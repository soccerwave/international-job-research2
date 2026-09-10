from __future__ import annotations

import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from src.runtime.artifacts import write_shard_bundle
from src.runtime.contracts import ShardDiagnostic, ShardStatus, utc_now_iso
from src.runtime.failure_classification import classify_failure
from src.runtime.live_shards import SHARD_IDS, _validate_rows

from src.runtime.production_sources import production_source_map
from src.sources.shared.pagination import capture_coverage

PRODUCTION_SHARD_IDS = SHARD_IDS
PRODUCER_VERSION = "V1.1_PAGINATED_DISCOVERY"
DEFAULT_PRODUCTION_MAX_JOBS_PER_SOURCE = None
PRODUCTION_HEARTBEAT_SECONDS = 30
_PROGRESS_LOCK = threading.Lock()


def _runtime_progress(event: str, **fields: Any) -> None:
    """Emit flushed source-lifecycle diagnostics without records, credentials, or environment dumps."""
    entry = {"timestamp": utc_now_iso(), "event": event, **fields}
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with _PROGRESS_LOCK:
        print("[production] " + line, file=sys.stderr, flush=True)
        raw_path = str(os.environ.get("PRODUCTION_PROGRESS_PATH") or "").strip()
        if raw_path:
            target = Path(raw_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()


@contextmanager
def _source_operation(*, run_id: str, shard_id: str, source_id: str, report_key: str):
    started = time.monotonic()
    done = threading.Event()
    common = {
        "run_id": run_id,
        "shard_id": shard_id,
        "source_id": source_id,
        "report_key": report_key,
    }
    _runtime_progress("source_start", **common)

    def heartbeat() -> None:
        while not done.wait(PRODUCTION_HEARTBEAT_SECONDS):
            _runtime_progress(
                "source_waiting",
                elapsed_seconds=round(time.monotonic() - started, 2),
                **common,
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        yield
    except Exception as exc:
        _runtime_progress(
            "source_error",
            error_type=type(exc).__name__,
            failure_class=classify_failure(exc),
            error=str(exc)[:1000],
            elapsed_seconds=round(time.monotonic() - started, 2),
            **common,
        )
        raise
    else:
        _runtime_progress(
            "source_collector_done",
            elapsed_seconds=round(time.monotonic() - started, 2),
            **common,
        )
    finally:
        done.set()
        thread.join()


def production_limit(default=None) -> int | None:
    """Uncapped by default; an explicit positive integer is a diagnostic override."""
    raw = str(os.environ.get("PRODUCTION_MAX_JOBS_PER_SOURCE") or default or "all").strip().lower()
    if raw in {"all", "none", "unlimited", "0"}:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("PRODUCTION_MAX_JOBS_PER_SOURCE must be all or a positive integer") from exc
    if value < 1:
        raise ValueError("PRODUCTION_MAX_JOBS_PER_SOURCE must be all or a positive integer")
    return value


def production_specs():
    return production_source_map(production_limit())


def run_production_shard(*, run_id: str, shard_id: str, output_root: Path) -> ShardDiagnostic:
    specs = production_specs()
    if shard_id not in specs:
        raise KeyError(f"Unknown production shard: {shard_id}")

    started_at = utc_now_iso()
    started = time.monotonic()
    records: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    for spec in specs[shard_id]:
        source_started = time.monotonic()
        try:
            with _source_operation(
                run_id=run_id,
                shard_id=shard_id,
                source_id=spec.source_id,
                report_key=spec.report_key,
            ):
                with capture_coverage() as coverage:
                    rows = spec.collector()
            _validate_rows(spec.source_id, rows)
            records.extend(rows)
            result_warnings = [
                f"Incomplete coverage: {event['source']}: {event['stop_reason']}"
                + (f" ({event['error']})" if event.get('error') else "")
                for event in coverage if not event['complete']
            ]
            failed_details = sum((row.get("description") or {}).get("detail_status") in
                                 {"FETCH_FAILED", "BLOCKED", "UNAVAILABLE"} for row in rows)
            if failed_details:
                result_warnings.append(f"Full description unavailable for {failed_details} records")
            if not rows:
                result_warnings.append(
                    "Zero observations in this production run; absence is not treated as closure or source failure."
                )
            source_results.append(
                {
                    "source_id": spec.source_id,
                    "report_key": spec.report_key,
                    "status": "PARTIAL" if result_warnings else "OK",
                    "coverage": coverage,
                    "records": len(rows),
                    "elapsed_ms": int((time.monotonic() - source_started) * 1000),
                    "warnings": result_warnings,
                    "error": "",
                    "failure_class": "",
                }
            )
            warnings.extend(f"{spec.source_id}: {item}" for item in result_warnings)
            _runtime_progress(
                "source_done",
                run_id=run_id,
                shard_id=shard_id,
                source_id=spec.source_id,
                report_key=spec.report_key,
                status="PARTIAL" if result_warnings else "OK",
                records=len(rows),
                warning_count=len(result_warnings),
                elapsed_ms=int((time.monotonic() - source_started) * 1000),
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            failure_class = classify_failure(exc)
            errors.append(f"{spec.source_id}: {message}")
            source_results.append(
                {
                    "source_id": spec.source_id,
                    "report_key": spec.report_key,
                    "status": "ERROR",
                    "records": 0,
                    "elapsed_ms": int((time.monotonic() - source_started) * 1000),
                    "warnings": [],
                    "error": message,
                    "failure_class": failure_class,
                }
            )
            _runtime_progress(
                "source_done",
                run_id=run_id,
                shard_id=shard_id,
                source_id=spec.source_id,
                report_key=spec.report_key,
                status="ERROR",
                failure_class=failure_class,
                records=0,
                warning_count=0,
                elapsed_ms=int((time.monotonic() - source_started) * 1000),
            )

    success_count = sum(item["status"] == "OK" for item in source_results)
    if success_count == len(source_results):
        status = ShardStatus.OK
    elif any(item["status"] != "ERROR" for item in source_results):
        status = ShardStatus.PARTIAL
    else:
        status = ShardStatus.ERROR

    detail_attempted = sum(
        1
        for row in records
        if str((row.get("description") or {}).get("detail_status") or "") != "NOT_ATTEMPTED"
    )
    detail_succeeded = sum(
        1
        for row in records
        if str((row.get("description") or {}).get("detail_status") or "") in {"FULL", "PARTIAL"}
    )
    diagnostic = ShardDiagnostic(
        shard_id=shard_id,
        source_ids=[spec.source_id for spec in specs[shard_id]],
        status=status,
        started_at=started_at,
        finished_at=utc_now_iso(),
        elapsed_ms=int((time.monotonic() - started) * 1000),
        records_observed=len(records),
        records_emitted=len(records),
        detail_attempted=detail_attempted,
        detail_succeeded=detail_succeeded,
        warnings=warnings,
        errors=errors,
        metadata={
            "source_results": source_results,
            "production_run": True,
            "collector_contract": "PAGINATED_PRODUCTION_DISCOVERY_V1.1",
            "max_jobs_per_source": production_limit(),
        },
    )
    write_shard_bundle(
        root=output_root,
        run_id=run_id,
        shard_id=shard_id,
        source_ids=[spec.source_id for spec in specs[shard_id]],
        records=records,
        diagnostic=diagnostic,
        producer_version=PRODUCER_VERSION,
    )
    return diagnostic
