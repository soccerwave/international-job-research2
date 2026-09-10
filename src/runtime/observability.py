from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from src.runtime.artifacts import verify_shard_bundle
from src.runtime.anomaly_detection import detect_runtime_anomalies


def _status_from(statuses: set[str]) -> str:
    normalized = {str(item or "UNKNOWN").upper() for item in statuses}
    if normalized == {"OK"}:
        return "OK"
    if "OK" in normalized or "PARTIAL" in normalized:
        return "PARTIAL"
    if "ERROR" in normalized:
        return "ERROR"
    if "MISSING" in normalized:
        return "MISSING"
    return "UNKNOWN"


def collect_run_observability(
    *,
    run_id: str,
    artifact_root: Path,
    expected_shards: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Build a read-only run-level view from immutable shard artifacts.

    This does not infer source health from absence. Missing shard artifacts are reported
    explicitly as MISSING and unexpected shard directories are surfaced separately.
    Logical sources that execute in multiple runtime shards (for example LinkedIn Europe)
    are aggregated while retaining per-shard instances.
    """
    expected = list(dict.fromkeys(expected_shards))
    expected_set = set(expected)
    run_dir = artifact_root / run_id / "shards"
    actual = sorted(
        path.parent.name
        for path in run_dir.glob("*/manifest.json")
    ) if run_dir.exists() else []
    actual_set = set(actual)
    missing = [shard_id for shard_id in expected if shard_id not in actual_set]
    unexpected = sorted(shard_id for shard_id in actual if shard_id not in expected_set)

    shard_rows: list[dict[str, Any]] = []
    source_acc: dict[str, dict[str, Any]] = {}

    def merge_source(
        *,
        key: str,
        shard_id: str,
        source_id: str,
        report_key: str,
        status: str,
        records: int,
        elapsed_ms: int,
        warnings: list[str],
        error: str,
        failure_class: str,
    ) -> None:
        row = source_acc.setdefault(
            key,
            {
                "logical_source": key,
                "status_set": set(),
                "records": 0,
                "elapsed_ms": 0,
                "shard_ids": [],
                "warnings": [],
                "errors": [],
                "failure_classes": set(),
                "instances": [],
            },
        )
        status_upper = str(status or "UNKNOWN").upper()
        row["status_set"].add(status_upper)
        row["records"] += int(records or 0)
        row["elapsed_ms"] += int(elapsed_ms or 0)
        if shard_id not in row["shard_ids"]:
            row["shard_ids"].append(shard_id)
        for warning in warnings:
            if warning and warning not in row["warnings"]:
                row["warnings"].append(warning)
        if error and error not in row["errors"]:
            row["errors"].append(error)
        if failure_class:
            row["failure_classes"].add(str(failure_class))
        row["instances"].append(
            {
                "shard_id": shard_id,
                "source_id": source_id,
                "report_key": report_key,
                "status": status_upper,
                "records": int(records or 0),
                "elapsed_ms": int(elapsed_ms or 0),
                "warning_count": len(warnings),
                "error": error,
                "failure_class": str(failure_class or ""),
            }
        )

    for shard_id in sorted(expected_set | actual_set):
        shard_dir = run_dir / shard_id
        if shard_id not in actual_set:
            shard_rows.append(
                {
                    "shard_id": shard_id,
                    "status": "MISSING",
                    "source_ids": [],
                    "started_at": "",
                    "finished_at": "",
                    "elapsed_ms": 0,
                    "records_observed": 0,
                    "records_emitted": 0,
                    "detail_attempted": 0,
                    "detail_succeeded": 0,
                    "warning_count": 0,
                    "error_count": 1,
                    "warnings": [],
                    "errors": ["MISSING_SHARD_ARTIFACT"],
                    "failure_classes": ["MISSING_ARTIFACT"],
                }
            )
            continue
        try:
            manifest, records, diagnostics = verify_shard_bundle(shard_dir)
        except Exception as exc:
            shard_rows.append(
                {
                    "shard_id": shard_id,
                    "status": "ERROR",
                    "source_ids": [],
                    "started_at": "",
                    "finished_at": "",
                    "elapsed_ms": 0,
                    "records_observed": 0,
                    "records_emitted": 0,
                    "detail_attempted": 0,
                    "detail_succeeded": 0,
                    "warning_count": 0,
                    "error_count": 1,
                    "warnings": [],
                    "errors": [f"INVALID_SHARD_ARTIFACT: {type(exc).__name__}: {exc}"],
                    "failure_classes": ["INVALID_ARTIFACT"],
                }
            )
            continue

        shard_warnings = list(diagnostics.get("warnings") or [])
        shard_errors = list(diagnostics.get("errors") or [])
        shard_rows.append(
            {
                "shard_id": shard_id,
                "status": manifest.status.value,
                "source_ids": list(manifest.source_ids),
                "started_at": str(diagnostics.get("started_at") or ""),
                "finished_at": str(diagnostics.get("finished_at") or ""),
                "elapsed_ms": int(diagnostics.get("elapsed_ms") or 0),
                "records_observed": int(diagnostics.get("records_observed") or len(records)),
                "records_emitted": int(diagnostics.get("records_emitted") or len(records)),
                "detail_attempted": int(diagnostics.get("detail_attempted") or 0),
                "detail_succeeded": int(diagnostics.get("detail_succeeded") or 0),
                "warning_count": len(shard_warnings),
                "error_count": len(shard_errors),
                "warnings": shard_warnings,
                "errors": shard_errors,
                "failure_classes": sorted({str(item.get("failure_class") or "") for item in ((diagnostics.get("metadata") or {}).get("source_results") or []) if item.get("failure_class")}),
            }
        )

        source_results = list(((diagnostics.get("metadata") or {}).get("source_results") or []))
        if source_results:
            for item in source_results:
                source_id = str(item.get("source_id") or "unknown")
                report_key = str(item.get("report_key") or source_id)
                item_warnings = list(item.get("warnings") or [])
                merge_source(
                    key=report_key,
                    shard_id=shard_id,
                    source_id=source_id,
                    report_key=report_key,
                    status=str(item.get("status") or manifest.status.value),
                    records=int(item.get("records") or 0),
                    elapsed_ms=int(item.get("elapsed_ms") or 0),
                    warnings=item_warnings,
                    error=str(item.get("error") or ""),
                    failure_class=str(item.get("failure_class") or ""),
                )
        else:
            for source_id in manifest.source_ids:
                matching = sum(
                    1
                    for record in records
                    if str((record.get("source") or {}).get("source_key") or "") == source_id
                )
                merge_source(
                    key=source_id,
                    shard_id=shard_id,
                    source_id=source_id,
                    report_key=source_id,
                    status=manifest.status.value,
                    records=matching,
                    elapsed_ms=int(diagnostics.get("elapsed_ms") or 0),
                    warnings=shard_warnings,
                    error="; ".join(shard_errors),
                    failure_class="UNKNOWN" if shard_errors else "",
                )

    source_rows: list[dict[str, Any]] = []
    for key in sorted(source_acc):
        row = source_acc[key]
        status = _status_from(set(row.pop("status_set")))
        source_rows.append(
            {
                "logical_source": key,
                "status": status,
                "records": row["records"],
                "elapsed_ms": row["elapsed_ms"],
                "shard_ids": sorted(row["shard_ids"]),
                "warning_count": len(row["warnings"]),
                "error_count": len(row["errors"]),
                "warnings": row["warnings"],
                "errors": row["errors"],
                "failure_classes": sorted(row["failure_classes"]),
                "instances": sorted(row["instances"], key=lambda item: (item["shard_id"], item["source_id"])),
            }
        )

    shard_status_counts = Counter(row["status"] for row in shard_rows)
    source_status_counts = Counter(row["status"] for row in source_rows)
    failure_class_counts = Counter(
        failure_class
        for row in source_rows
        for failure_class in row.get("failure_classes", [])
    )
    for row in shard_rows:
        if row["status"] in {"MISSING", "ERROR"} and not row.get("source_ids"):
            failure_class_counts.update(row.get("failure_classes", []))
    anomalies = detect_runtime_anomalies(
        run_id=run_id,
        artifact_root=artifact_root,
        shard_rows=shard_rows,
        source_rows=source_rows,
        missing_shards=missing,
        unexpected_shards=unexpected,
    )
    return {
        "version": 1,
        "run_id": run_id,
        "expected_shards": len(expected),
        "artifacts_present": len(actual),
        "missing_shards": missing,
        "unexpected_shards": unexpected,
        "shard_status_counts": dict(sorted(shard_status_counts.items())),
        "source_status_counts": dict(sorted(source_status_counts.items())),
        "failure_class_counts": dict(sorted(failure_class_counts.items())),
        "runtime_anomalies": anomalies,
        "totals": {
            "records_observed": sum(int(row["records_observed"]) for row in shard_rows),
            "records_emitted": sum(int(row["records_emitted"]) for row in shard_rows),
            "detail_attempted": sum(int(row["detail_attempted"]) for row in shard_rows),
            "detail_succeeded": sum(int(row["detail_succeeded"]) for row in shard_rows),
            "shard_elapsed_ms_sum": sum(int(row["elapsed_ms"]) for row in shard_rows),
            "source_elapsed_ms_sum": sum(int(row["elapsed_ms"]) for row in source_rows),
            "warning_count": sum(int(row["warning_count"]) for row in shard_rows),
            "error_count": sum(int(row["error_count"]) for row in shard_rows),
        },
        "shards": shard_rows,
        "sources": source_rows,
    }
