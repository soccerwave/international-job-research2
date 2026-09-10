from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("code") or ""),
            str(row.get("shard_id") or ""),
            str(row.get("source_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def detect_runtime_anomalies(
    *,
    run_id: str,
    artifact_root: Path,
    shard_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    missing_shards: list[str],
    unexpected_shards: list[str],
) -> dict[str, Any]:
    """Detect structural runtime anomalies without changing production behavior."""
    anomalies: list[dict[str, Any]] = []

    for shard_id in missing_shards:
        anomalies.append({
            "code": "MISSING_SHARD_ARTIFACT",
            "severity": "ERROR",
            "shard_id": shard_id,
            "source_id": "",
            "detail": "Expected shard artifact is missing.",
        })

    for shard_id in unexpected_shards:
        anomalies.append({
            "code": "UNEXPECTED_SHARD_ARTIFACT",
            "severity": "WARNING",
            "shard_id": shard_id,
            "source_id": "",
            "detail": "Unexpected shard artifact is present.",
        })

    for source in source_rows:
        for instance in source.get("instances") or []:
            if str(instance.get("status") or "").upper() == "ERROR":
                anomalies.append({
                    "code": "SOURCE_ERROR",
                    "severity": "ERROR",
                    "shard_id": str(instance.get("shard_id") or ""),
                    "source_id": str(instance.get("source_id") or ""),
                    "detail": str(instance.get("failure_class") or "UNKNOWN"),
                })

    diagnostics_root = artifact_root / run_id / "diagnostics"
    if diagnostics_root.exists():
        for lifecycle_path in sorted(diagnostics_root.glob("*/source_lifecycle.jsonl")):
            shard_id = lifecycle_path.parent.name
            active: dict[tuple[str, str], int] = {}
            for line_number, raw in enumerate(lifecycle_path.read_text(encoding="utf-8").splitlines(), start=1):
                if not raw.strip():
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    anomalies.append({
                        "code": "MALFORMED_LIFECYCLE_EVENT",
                        "severity": "WARNING",
                        "shard_id": shard_id,
                        "source_id": "",
                        "detail": f"Invalid JSON at line {line_number}.",
                    })
                    continue

                source_id = str(event.get("source_id") or "")
                report_key = str(event.get("report_key") or source_id)
                key = (source_id, report_key)
                name = str(event.get("event") or "")

                if name == "source_start":
                    active[key] = active.get(key, 0) + 1
                elif name == "source_done":
                    if active.get(key, 0) > 0:
                        active[key] -= 1
                    else:
                        anomalies.append({
                            "code": "ORPHAN_SOURCE_DONE",
                            "severity": "WARNING",
                            "shard_id": shard_id,
                            "source_id": source_id,
                            "detail": "source_done observed without matching source_start.",
                        })
                elif name == "source_error":
                    anomalies.append({
                        "code": "LIFECYCLE_SOURCE_ERROR",
                        "severity": "ERROR",
                        "shard_id": shard_id,
                        "source_id": source_id,
                        "detail": str(event.get("failure_class") or event.get("error_type") or "UNKNOWN"),
                    })

            for (source_id, _report_key), count in active.items():
                if count > 0:
                    anomalies.append({
                        "code": "INCOMPLETE_SOURCE_LIFECYCLE",
                        "severity": "ERROR",
                        "shard_id": shard_id,
                        "source_id": source_id,
                        "detail": f"{count} source_start event(s) have no matching source_done.",
                    })

    anomalies = _dedupe(anomalies)
    code_counts = Counter(str(row["code"]) for row in anomalies)
    severity_counts = Counter(str(row["severity"]) for row in anomalies)

    return {
        "version": 1,
        "status": "ANOMALIES_DETECTED" if anomalies else "NO_ANOMALIES",
        "count": len(anomalies),
        "code_counts": dict(sorted(code_counts.items())),
        "severity_counts": dict(sorted(severity_counts.items())),
        "items": anomalies,
        "behavior": "OBSERVE_ONLY",
    }
