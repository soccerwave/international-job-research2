from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3

CONTROL_PLANE_POINTER_VERSION = "CONTROL_PLANE_REPORT_POINTER_V1.0.0"
DEFAULT_PREFIX = "control-plane"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_inputs(summary_path: Path, report_path: Path) -> tuple[dict[str, Any], bytes, bytes]:
    summary_bytes = summary_path.read_bytes()
    report_bytes = report_path.read_bytes()
    summary = json.loads(summary_bytes.decode("utf-8"))
    if not isinstance(summary, dict):
        raise ValueError("report summary must be a JSON object")
    if not str(summary.get("run_id") or "").strip():
        raise ValueError("report summary is missing run_id")
    if not report_bytes:
        raise ValueError("Excel report is empty")
    return summary, summary_bytes, report_bytes


def build_manifest(
    *,
    summary_path: Path,
    report_path: Path,
    github_run_id: int,
    github_run_attempt: int,
    commit: str,
    prefix: str = DEFAULT_PREFIX,
    published_at: str | None = None,
    audit_report_path: Path | None = None,
) -> dict[str, Any]:
    summary, summary_bytes, report_bytes = _load_inputs(summary_path, report_path)
    run_key = f"{prefix.rstrip('/')}/runs/{github_run_id}-{github_run_attempt}"
    manifest = {
        "schema_version": CONTROL_PLANE_POINTER_VERSION,
        "project": "international",
        "github_run_id": int(github_run_id),
        "github_run_attempt": int(github_run_attempt),
        "production_run_id": str(summary["run_id"]),
        "commit": str(commit or ""),
        "published_at": published_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary_key": f"{run_key}/report_summary.json",
        "report_key": f"{run_key}/international_academic_job_report.xlsx",
        "summary_sha256": sha256_bytes(summary_bytes),
        "report_sha256": sha256_bytes(report_bytes),
        "summary_bytes": len(summary_bytes),
        "report_bytes": len(report_bytes),
        "report_variant": "USER_CLEAN_V1",
        "records_observed": int(summary.get("records_observed") or 0),
        "current_actionable": int(summary.get("current_actionable") or 0),
        "today_actionable": int(summary.get("today_actionable") or 0),
        "state_generation": int(summary.get("state_generation") or 0),
    }
    if audit_report_path is not None:
        audit_bytes = audit_report_path.read_bytes()
        if not audit_bytes:
            raise ValueError("audit Excel report is empty")
        manifest.update(
            {
                "audit_report_key": f"{run_key}/international_academic_job_audit.xlsx",
                "audit_report_sha256": sha256_bytes(audit_bytes),
                "audit_report_bytes": len(audit_bytes),
            }
        )
    return manifest


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


def publish_report(
    *,
    client,
    bucket: str,
    summary_path: Path,
    report_path: Path,
    github_run_id: int,
    github_run_attempt: int,
    commit: str,
    prefix: str = DEFAULT_PREFIX,
    manifest_out: Path | None = None,
    audit_report_path: Path | None = None,
) -> dict[str, Any]:
    summary, summary_bytes, report_bytes = _load_inputs(summary_path, report_path)
    manifest = build_manifest(
        summary_path=summary_path,
        report_path=report_path,
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        commit=commit,
        prefix=prefix,
        audit_report_path=audit_report_path,
    )

    # Publish immutable run-scoped payloads first. The latest pointer is written last,
    # so the bot can never observe a pointer to a half-published report set.
    client.put_object(
        Bucket=bucket,
        Key=manifest["summary_key"],
        Body=summary_bytes,
        ContentType="application/json; charset=utf-8",
        Metadata={"sha256": manifest["summary_sha256"], "project": "international"},
    )
    client.put_object(
        Bucket=bucket,
        Key=manifest["report_key"],
        Body=report_bytes,
        ContentType=XLSX_CONTENT_TYPE,
        Metadata={"sha256": manifest["report_sha256"], "project": "international", "variant": "user-clean"},
    )

    audit_bytes: bytes | None = None
    if audit_report_path is not None:
        audit_bytes = audit_report_path.read_bytes()
        client.put_object(
            Bucket=bucket,
            Key=manifest["audit_report_key"],
            Body=audit_bytes,
            ContentType=XLSX_CONTENT_TYPE,
            Metadata={"sha256": manifest["audit_report_sha256"], "project": "international", "variant": "audit"},
        )

    summary_head = client.head_object(Bucket=bucket, Key=manifest["summary_key"])
    report_head = client.head_object(Bucket=bucket, Key=manifest["report_key"])
    if int(summary_head.get("ContentLength") or -1) != len(summary_bytes):
        raise RuntimeError("R2 summary read-back size mismatch")
    if int(report_head.get("ContentLength") or -1) != len(report_bytes):
        raise RuntimeError("R2 report read-back size mismatch")
    if audit_bytes is not None:
        audit_head = client.head_object(Bucket=bucket, Key=manifest["audit_report_key"])
        if int(audit_head.get("ContentLength") or -1) != len(audit_bytes):
            raise RuntimeError("R2 audit report read-back size mismatch")

    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    latest_key = f"{prefix.rstrip('/')}/latest/manifest.json"
    client.put_object(
        Bucket=bucket,
        Key=latest_key,
        Body=manifest_bytes,
        ContentType="application/json; charset=utf-8",
        Metadata={"project": "international", "schema": CONTROL_PLANE_POINTER_VERSION},
    )

    latest = client.get_object(Bucket=bucket, Key=latest_key)
    readback = json.loads(latest["Body"].read().decode("utf-8"))
    if readback != manifest:
        raise RuntimeError("R2 latest control-plane manifest read-back mismatch")

    result = {
        "status": "PASS",
        "bucket": bucket,
        "latest_manifest_key": latest_key,
        "manifest": manifest,
        "summary_records_observed": int(summary.get("records_observed") or 0),
    }
    if manifest_out is not None:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish the latest international report set for the shared Telegram control plane")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path)
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
    result = publish_report(
        client=build_r2_client(),
        bucket=bucket,
        summary_path=args.summary,
        report_path=args.report,
        audit_report_path=args.audit_report,
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
