from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3

POINTER_VERSION = "LLM_SHADOW_REPORT_POINTER_V0.1"
DEFAULT_PREFIX = "llm/reports"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _required_file(path: Path, label: str) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(f"{label} file is missing: {path}")
    data = path.read_bytes()
    if not data:
        raise ValueError(f"{label} file is empty: {path}")
    return data


def build_manifest(
    *,
    summary_path: Path,
    report_path: Path,
    production_run_id: str,
    github_run_id: int,
    github_run_attempt: int,
    commit: str,
    prefix: str = DEFAULT_PREFIX,
    published_at: str | None = None,
) -> dict[str, Any]:
    summary_bytes = _required_file(summary_path, "shadow summary")
    report_bytes = _required_file(report_path, "shadow report")
    summary = json.loads(summary_bytes.decode("utf-8"))
    if not isinstance(summary, dict):
        raise ValueError("shadow summary must be a JSON object")
    if str(summary.get("run_id") or "") != str(production_run_id):
        raise ValueError("shadow summary run_id does not match production_run_id")

    run_key = f"{prefix.rstrip('/')}/runs/{github_run_id}-{github_run_attempt}"
    return {
        "schema_version": POINTER_VERSION,
        "project": "international",
        "report_variant": "LLM_SHADOW_V0.1",
        "production_run_id": str(production_run_id),
        "github_run_id": int(github_run_id),
        "github_run_attempt": int(github_run_attempt),
        "commit": str(commit or ""),
        "model": str(summary.get("model") or ""),
        "candidate_profile_version": str(summary.get("candidate_profile_version") or ""),
        "published_at": published_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary_key": f"{run_key}/shadow_summary.json",
        "report_key": f"{run_key}/llm_shadow_report.xlsx",
        "summary_sha256": _sha256(summary_bytes),
        "report_sha256": _sha256(report_bytes),
        "summary_bytes": len(summary_bytes),
        "report_bytes": len(report_bytes),
        "main_rows": int(((summary.get("report") or {}).get("main_rows") or 0)),
        "llm_rescued_rows": int(((summary.get("report") or {}).get("llm_rescued_rows") or 0)),
        "disagreement_rows": int(((summary.get("report") or {}).get("disagreement_rows") or 0)),
        "failures": int(summary.get("failures") or 0),
        "shadow_only": bool(summary.get("shadow_only")),
        "production_authority_unchanged": bool(summary.get("production_authority_unchanged")),
    }


def build_r2_client():
    account_id = str(os.getenv("R2_ACCOUNT_ID") or "").strip()
    access_key = str(os.getenv("R2_ACCESS_KEY_ID") or "").strip()
    secret_key = str(os.getenv("R2_SECRET_ACCESS_KEY") or "").strip()
    endpoint = str(os.getenv("R2_ENDPOINT") or "").strip()
    if not endpoint and account_id:
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    missing = [
        name
        for name, value in {
            "R2_ACCOUNT_ID": account_id,
            "R2_ACCESS_KEY_ID": access_key,
            "R2_SECRET_ACCESS_KEY": secret_key,
            "R2_ENDPOINT": endpoint,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("Missing R2 configuration: " + ", ".join(missing))
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def publish_llm_shadow_report(
    *,
    client,
    bucket: str,
    summary_path: Path,
    report_path: Path,
    production_run_id: str,
    github_run_id: int,
    github_run_attempt: int,
    commit: str,
    prefix: str = DEFAULT_PREFIX,
    manifest_out: Path | None = None,
) -> dict[str, Any]:
    summary_bytes = _required_file(summary_path, "shadow summary")
    report_bytes = _required_file(report_path, "shadow report")
    manifest = build_manifest(
        summary_path=summary_path,
        report_path=report_path,
        production_run_id=production_run_id,
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        commit=commit,
        prefix=prefix,
    )

    # Write the immutable run-scoped payloads first.
    client.put_object(
        Bucket=bucket,
        Key=manifest["summary_key"],
        Body=summary_bytes,
        ContentType="application/json; charset=utf-8",
        Metadata={
            "sha256": manifest["summary_sha256"],
            "project": "international",
            "variant": "llm-shadow",
        },
    )
    client.put_object(
        Bucket=bucket,
        Key=manifest["report_key"],
        Body=report_bytes,
        ContentType=XLSX_CONTENT_TYPE,
        Metadata={
            "sha256": manifest["report_sha256"],
            "project": "international",
            "variant": "llm-shadow",
        },
    )

    summary_head = client.head_object(Bucket=bucket, Key=manifest["summary_key"])
    report_head = client.head_object(Bucket=bucket, Key=manifest["report_key"])
    if int(summary_head.get("ContentLength") or -1) != len(summary_bytes):
        raise RuntimeError("R2 shadow summary read-back size mismatch")
    if int(report_head.get("ContentLength") or -1) != len(report_bytes):
        raise RuntimeError("R2 shadow report read-back size mismatch")

    # Publish latest pointer only after both payloads are durably present.
    latest_key = f"{prefix.rstrip('/')}/latest/manifest.json"
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    client.put_object(
        Bucket=bucket,
        Key=latest_key,
        Body=manifest_bytes,
        ContentType="application/json; charset=utf-8",
        Metadata={
            "project": "international",
            "schema": POINTER_VERSION,
            "variant": "llm-shadow",
        },
    )

    latest = client.get_object(Bucket=bucket, Key=latest_key)
    readback = json.loads(latest["Body"].read().decode("utf-8"))
    if readback != manifest:
        raise RuntimeError("R2 latest LLM shadow manifest read-back mismatch")

    result = {
        "status": "PASS",
        "bucket": bucket,
        "latest_manifest_key": latest_key,
        "latest_report_key": manifest["report_key"],
        "latest_summary_key": manifest["summary_key"],
        "manifest": manifest,
    }
    if manifest_out is not None:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish the latest International LLM shadow report to R2"
    )
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--production-run-id", required=True)
    parser.add_argument("--github-run-id", type=int, required=True)
    parser.add_argument("--github-run-attempt", type=int, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--manifest-out", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bucket = str(os.getenv("R2_BUCKET") or "").strip()
    if not bucket:
        raise SystemExit("R2_BUCKET is required")
    result = publish_llm_shadow_report(
        client=build_r2_client(),
        bucket=bucket,
        summary_path=args.summary,
        report_path=args.report,
        production_run_id=args.production_run_id,
        github_run_id=args.github_run_id,
        github_run_attempt=args.github_run_attempt,
        commit=args.commit,
        prefix=args.prefix,
        manifest_out=args.manifest_out,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
