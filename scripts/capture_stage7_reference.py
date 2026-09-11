from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
ROSTER_PATH = ROOT / "config" / "reference" / "stage7_reference_roster_v1.json"
MANIFEST_PATH = ROOT / "data" / "reference" / "stage7" / "reference_set_manifest_v1.json"
VACANCY_SCHEMA_PATH = ROOT / "schemas" / "reference_vacancy.schema.json"
CAPTURE_SCHEMA_PATH = ROOT / "schemas" / "reference_capture.schema.json"

REFERENCE_PREFIX = "stage7/reference/v1/"
OBSERVATIONS_KEY = REFERENCE_PREFIX + "reference_observations_v1.jsonl.enc"
CAPTURE_LOG_KEY = REFERENCE_PREFIX + "reference_capture_log_v1.jsonl.enc"

ROLE_OR_JOB_TEXT = re.compile(
    r"\b(?:post\s*-?\s*doc(?:toral)?|research\s+fellow|research\s+associate|"
    r"assistant\s+professor|lecturer|tenure\s*-?\s*track|junior\s+profess|"
    r"research\s+scientist|researcher|university\s+assistant|academic\s+position|"
    r"vacanc(?:y|ies)|job\s+offer|job\s+opening|career\s+opportunit)\b",
    re.I,
)
JOBISH_URL = re.compile(
    r"(?:/|\b)(?:jobs?|vacanc(?:y|ies)|positions?|careers?|emploi|stellen|recruit|"
    r"listing|opportunit|postdoc|academic)(?:/|\b|[-_?=&])",
    re.I,
)
NEXT_TEXT = re.compile(r"^(?:next|next page|weiter|suivant|volgende|nächste|›|»|>)$", re.I)
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_url(base_url: str, href: str) -> str | None:
    href = _compact(href)
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            urlencode(query, doseq=True),
            "",
        )
    )


def is_candidate_anchor(base_url: str, href: str, text: str) -> bool:
    normalized = normalize_url(base_url, href)
    label = _compact(text)
    if normalized is None or len(label) < 3:
        return False
    return bool(JOBISH_URL.search(normalized) or ROLE_OR_JOB_TEXT.search(label))


def reference_id(source_id: str, normalized_url: str) -> str:
    digest = hashlib.sha256(f"{source_id}|{normalized_url}".encode("utf-8")).hexdigest()[:24]
    return f"ref-{digest}"


def _capture_id(source_id: str, capture_date: str) -> str:
    return f"cap-{capture_date}-{source_id}"


def _build_r2_client():
    account_id = str(os.getenv("R2_ACCOUNT_ID") or "").strip()
    endpoint = str(os.getenv("R2_ENDPOINT") or "").strip()
    access_key = str(os.getenv("R2_ACCESS_KEY_ID") or "").strip()
    secret_key = str(os.getenv("R2_SECRET_ACCESS_KEY") or "").strip()
    if not endpoint and account_id:
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    missing = [
        name
        for name, value in {
            "R2_ACCOUNT_ID": account_id,
            "R2_ENDPOINT": endpoint,
            "R2_ACCESS_KEY_ID": access_key,
            "R2_SECRET_ACCESS_KEY": secret_key,
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


def _decrypt_file(encrypted: Path, plain: Path) -> None:
    if not str(os.getenv("ARTIFACT_ENCRYPTION_KEY") or "").strip():
        raise RuntimeError("ARTIFACT_ENCRYPTION_KEY is required")
    subprocess.run(
        [
            "openssl",
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-pass",
            "env:ARTIFACT_ENCRYPTION_KEY",
            "-in",
            str(encrypted),
            "-out",
            str(plain),
        ],
        check=True,
    )


def _encrypt_file(plain: Path, encrypted: Path) -> None:
    if not str(os.getenv("ARTIFACT_ENCRYPTION_KEY") or "").strip():
        raise RuntimeError("ARTIFACT_ENCRYPTION_KEY is required")
    subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-pbkdf2",
            "-salt",
            "-pass",
            "env:ARTIFACT_ENCRYPTION_KEY",
            "-in",
            str(plain),
            "-out",
            str(encrypted),
        ],
        check=True,
    )


def _read_private_jsonl(client, bucket: str, key: str, workdir: Path) -> list[dict[str, Any]]:
    encrypted = workdir / (Path(key).name + ".download")
    plain = workdir / (Path(key).name + ".plain")
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str((exc.response.get("Error") or {}).get("Code") or "")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return []
        raise
    encrypted.write_bytes(response["Body"].read())
    _decrypt_file(encrypted, plain)
    records: list[dict[str, Any]] = []
    for number, line in enumerate(plain.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{key} line {number} is not a JSON object")
        records.append(value)
    return records


def _write_private_jsonl(
    client,
    bucket: str,
    key: str,
    records: list[dict[str, Any]],
    workdir: Path,
) -> dict[str, Any]:
    plain = workdir / (Path(key).name + ".plain-out")
    encrypted = workdir / (Path(key).name + ".upload")
    payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    plain.write_text(payload, encoding="utf-8")
    plaintext_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    _encrypt_file(plain, encrypted)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=encrypted.read_bytes(),
        ContentType="application/octet-stream",
        Metadata={
            "plaintext-sha256": plaintext_sha256,
            "record-count": str(len(records)),
            "storage": "encrypted-private-stage7-reference",
        },
    )
    head = client.head_object(Bucket=bucket, Key=key)
    size = int(head.get("ContentLength") or 0)
    if size <= 0:
        raise RuntimeError(f"R2 read-back size is invalid for {key}")
    return {"encrypted_bytes": size, "plaintext_sha256": plaintext_sha256, "record_count": len(records)}


def _extract_anchors(page) -> list[dict[str, str]]:
    return page.locator("a").evaluate_all(
        """els => els.map(a => ({
          href: a.href || a.getAttribute('href') || '',
          text: (a.innerText || a.getAttribute('aria-label') || a.getAttribute('title') || '').trim(),
          rel: a.getAttribute('rel') || ''
        }))"""
    )


def _find_next_url(current_url: str, anchors: list[dict[str, str]], visited: set[str]) -> str | None:
    current_host = urlparse(current_url).netloc.lower()
    for anchor in anchors:
        text = _compact(anchor.get("text"))
        rel = _compact(anchor.get("rel")).lower()
        if "next" not in rel.split() and not NEXT_TEXT.match(text):
            continue
        candidate = normalize_url(current_url, anchor.get("href") or "")
        if candidate is None or candidate in visited:
            continue
        if urlparse(candidate).netloc.lower() != current_host:
            continue
        return candidate
    return None


def capture_source(browser, source: dict[str, Any], capture_date: str, observed_at: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_id = str(source["reference_source_id"])
    country = str(source["country_code"])
    surface_url = str(source["url"])
    page = browser.new_page()
    page.set_default_timeout(12000)
    anchors_seen: dict[str, str] = {}
    visited: set[str] = set()
    fingerprint = hashlib.sha256()
    status = "CAPTURED_PARTIAL"
    note = "Independent browser capture completed; generic pagination and dynamic-load completeness are not yet certified."
    try:
        current_url = surface_url
        for _page_number in range(5):
            if current_url in visited:
                break
            visited.add(current_url)
            response = page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
            http_status = int(response.status) if response is not None else 0
            if http_status in {401, 403, 429}:
                status = "ACCESS_BLOCKED"
                note = f"Independent browser capture blocked with HTTP {http_status}; no completeness claim."
                break
            if http_status >= 500:
                status = "SOURCE_UNAVAILABLE"
                note = f"Reference surface returned HTTP {http_status}; no completeness claim."
                break
            page.wait_for_timeout(1200)
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(600)
            html = page.content()
            fingerprint.update(hashlib.sha256(html.encode("utf-8", errors="replace")).digest())
            anchors = _extract_anchors(page)
            for anchor in anchors:
                href = str(anchor.get("href") or "")
                text = _compact(anchor.get("text"))
                if not is_candidate_anchor(current_url, href, text):
                    continue
                normalized = normalize_url(current_url, href)
                if normalized is not None:
                    anchors_seen.setdefault(normalized, text)
            next_url = _find_next_url(current_url, anchors, visited)
            if not next_url:
                break
            current_url = next_url
    except Exception as exc:
        status = "RETRY_REQUIRED"
        note = f"Independent browser capture raised {type(exc).__name__}; retry/manual review required."
    finally:
        page.close()

    if status == "CAPTURED_PARTIAL" and not anchors_seen:
        status = "PARSER_NOT_APPLICABLE_MANUAL_REVIEW"
        note = "Surface loaded but no vacancy-like anchors were extracted; manual review required."

    source_fingerprint = fingerprint.hexdigest() if visited else None
    observations = [
        {
            "reference_id": reference_id(source_id, url),
            "reference_source_id": source_id,
            "reference_url": url,
            "observed_at": observed_at,
            "title": title,
            "institution": None,
            "country_code": country,
            "posted_at": None,
            "deadline_at": None,
            "role_family_or_pending": "PENDING_ADJUDICATION",
            "eligibility_status": "PENDING_ADJUDICATION",
            "eligibility_reason": "Independent Stage 7.2 browser capture; eligibility adjudication pending.",
            "evidence_note": "Captured independently from the frozen reference surface; not sourced from production output or collector code.",
            "raw_snapshot_fingerprint": source_fingerprint,
        }
        for url, title in sorted(anchors_seen.items())
    ]
    capture = {
        "capture_id": _capture_id(source_id, capture_date),
        "reference_source_id": source_id,
        "country_code": country,
        "capture_date": capture_date,
        "captured_at": observed_at,
        "status": status,
        "surface_url": surface_url,
        "observation_count": len(observations),
        "evidence_note": note,
        "snapshot_fingerprint": source_fingerprint,
        "retry_of_capture_id": None,
    }
    return observations, capture


def main() -> int:
    manifest = _load_json(MANIFEST_PATH)
    roster = _load_json(ROSTER_PATH)
    vacancy_schema = _load_json(VACANCY_SCHEMA_PATH)
    capture_schema = _load_json(CAPTURE_SCHEMA_PATH)
    vacancy_validator = Draft202012Validator(vacancy_schema)
    capture_validator = Draft202012Validator(capture_schema)

    timezone_name = str(manifest["window"]["timezone"])
    now = datetime.now(ZoneInfo(timezone_name))
    capture_date = now.date().isoformat()
    start_date = str(manifest["window"]["start_date"])
    end_date = str(manifest["window"]["end_date"])
    if capture_date < start_date or capture_date > end_date:
        print(json.dumps({"status": "NOOP_OUTSIDE_WINDOW", "capture_date": capture_date}))
        return 0

    bucket = str(os.getenv("R2_BUCKET") or "").strip()
    if not bucket:
        raise RuntimeError("R2_BUCKET is required")
    client = _build_r2_client()

    with tempfile.TemporaryDirectory(prefix="stage7-reference-") as temp:
        workdir = Path(temp)
        existing_observations = _read_private_jsonl(client, bucket, OBSERVATIONS_KEY, workdir)
        existing_captures = _read_private_jsonl(client, bucket, CAPTURE_LOG_KEY, workdir)
        observation_by_id = {str(item["reference_id"]): item for item in existing_observations}
        existing_capture_ids = {str(item["capture_id"]) for item in existing_captures}

        pending_sources = [
            source
            for source in roster["sources"]
            if _capture_id(str(source["reference_source_id"]), capture_date) not in existing_capture_ids
        ]
        new_captures: list[dict[str, Any]] = []
        new_observations = 0
        observed_at = now.isoformat()

        if pending_sources:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    for source in pending_sources:
                        observations, capture = capture_source(browser, source, capture_date, observed_at)
                        capture_validator.validate(capture)
                        new_captures.append(capture)
                        for observation in observations:
                            vacancy_validator.validate(observation)
                            ref_id = str(observation["reference_id"])
                            if ref_id not in observation_by_id:
                                observation_by_id[ref_id] = observation
                                new_observations += 1
                finally:
                    browser.close()

        final_observations = list(observation_by_id.values())
        final_captures = existing_captures + new_captures
        observation_write = _write_private_jsonl(
            client, bucket, OBSERVATIONS_KEY, final_observations, workdir
        )
        capture_write = _write_private_jsonl(
            client, bucket, CAPTURE_LOG_KEY, final_captures, workdir
        )

    status_counts = Counter(str(item.get("status") or "UNKNOWN") for item in new_captures)
    print(
        json.dumps(
            {
                "status": "PASS",
                "capture_date": capture_date,
                "pending_source_count": len(pending_sources),
                "new_capture_event_count": len(new_captures),
                "new_unique_observation_count": new_observations,
                "total_unique_observation_count": observation_write["record_count"],
                "total_capture_event_count": capture_write["record_count"],
                "capture_status_counts": dict(sorted(status_counts.items())),
                "observations_encrypted_bytes": observation_write["encrypted_bytes"],
                "capture_log_encrypted_bytes": capture_write["encrypted_bytes"],
                "raw_snapshots_persisted": False,
                "pipeline_output_used": False,
                "pipeline_collector_code_used": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
