from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.evaluation.evaluator import evaluate_vacancy
from src.reporting.report import build_reporting_payload, build_xlsx, write_summary_json
from src.runtime.artifacts import atomic_create_bytes, verify_shard_bundle
from src.runtime.canonicalizer import canonicalize_records
from src.runtime.finalizer import finalize_run
from src.runtime.state_projection import build_state_identity_projection, sync_state_annotations
from src.runtime.state_writer import FinalizerStateWriter
from src.state.r2_store import R2StateStore

PREPROD_CONTRACT_VERSION = "PREPROD_RC1_CONTRACT_V1.0.0"
ROOT = Path(__file__).resolve().parents[2]
VACANCY_SCHEMA = json.loads((ROOT / "schemas" / "vacancy.schema.json").read_text(encoding="utf-8"))
VACANCY_VALIDATOR = Draft202012Validator(VACANCY_SCHEMA)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _parse_iso(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def apply_central_availability(record: dict[str, Any], *, observed_at: str) -> dict[str, Any]:
    """Apply only explicit deadline/status evidence; absence never closes a vacancy."""
    source = record.get("source") or {}
    dates = record.get("dates") or {}
    status_before = str(source.get("source_status") or "UNKNOWN").upper()
    status_after = status_before
    reason = "SOURCE_STATUS_PRESERVED"

    if status_before not in {"CLOSED", "ERROR"}:
        deadline_status = str(dates.get("deadline_status") or "UNKNOWN").upper()
        deadline_at = str(dates.get("deadline_at") or "").strip()
        if deadline_status == "KNOWN" and deadline_at:
            try:
                deadline = _parse_iso(deadline_at)
                observed = _parse_iso(observed_at)
                if deadline < observed:
                    status_after = "CLOSED"
                    reason = "EXPLICIT_DEADLINE_PASSED"
                elif status_before == "UNKNOWN":
                    status_after = "OPEN"
                    reason = "EXPLICIT_FUTURE_DEADLINE"
            except ValueError:
                reason = "DEADLINE_PARSE_UNRESOLVED"
        elif deadline_status in {"ROLLING", "OPEN_UNTIL_FILLED"} and status_before == "UNKNOWN":
            status_after = "OPEN"
            reason = f"EXPLICIT_{deadline_status}"

    source["source_status"] = status_after
    record["source"] = source
    record.setdefault("raw_extra", {})["availability"] = {
        "resolver": "STAGE10_CENTRAL_EXPLICIT_EVIDENCE_ONLY",
        "observed_at": observed_at,
        "source_status_before": status_before,
        "source_status_after": status_after,
        "reason": reason,
        "absence_inference": "DISABLED",
    }
    return record


def _prepare_for_evaluation(record: dict[str, Any]) -> None:
    """Convert collector-stage routing metadata into evaluator-ready policy metadata."""
    classification = record.setdefault("classification", {})
    review_codes = [
        code for code in (classification.get("review_codes") or [])
        if str(code) != "COLLECTOR_ONLY_NOT_PRE_EVALUATED"
    ]
    classification["review_codes"] = review_codes
    blockers = list(classification.get("blocker_codes") or [])
    detail_status = str((record.get("description") or {}).get("detail_status") or "NOT_ATTEMPTED").upper()

    if blockers:
        classification["pre_evaluation_disposition"] = "POLICY_SKIP"
    elif detail_status not in {"FULL", "PARTIAL"}:
        classification["pre_evaluation_disposition"] = "NEEDS_DETAIL_REVIEW"
    elif review_codes:
        classification["pre_evaluation_disposition"] = "POLICY_REVIEW"
    else:
        classification["pre_evaluation_disposition"] = "ELIGIBLE_FOR_EVALUATION"

    canonicalization = (record.get("raw_extra") or {}).get("canonicalization") or {}
    if canonicalization.get("source_status_conflict"):
        review_codes = list(classification.get("review_codes") or [])
        if "SOURCE_STATUS_CONFLICT" not in review_codes:
            review_codes.append("SOURCE_STATUS_CONFLICT")
        classification["review_codes"] = review_codes
        if not blockers:
            classification["pre_evaluation_disposition"] = "POLICY_REVIEW"


def evaluate_canonical_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for record in records:
        _prepare_for_evaluation(record)
        record.setdefault("raw_extra", {})["evaluation"] = evaluate_vacancy(record)
    return records


def _validate_canonical(records: list[dict[str, Any]]) -> None:
    failures: list[str] = []
    for index, record in enumerate(records):
        errors = list(VACANCY_VALIDATOR.iter_errors(record))
        if errors:
            failures.append(f"record[{index}]: " + "; ".join(error.message for error in errors[:4]))
    if failures:
        raise RuntimeError("Canonical vacancy schema validation failed: " + " | ".join(failures[:5]))


def persist_preprod_state(
    records: list[dict[str, Any]],
    *,
    state_backend: str,
    observed_at: str,
    run_id: str,
    state_path: Path | None = None,
    r2_store: R2StateStore | None = None,
    allow_bootstrap: bool = False,
):
    """Persist Stage 10 state through a collision-safe identity projection."""
    projected, projection_summary = build_state_identity_projection(records)
    backend = state_backend.strip().upper()

    if backend == "LOCAL":
        if state_path is None:
            raise ValueError("state_path is required for LOCAL state backend")
        state_result = FinalizerStateWriter.persist_local(
            projected,
            state_path=state_path,
            observed_at=observed_at,
            run_id=run_id,
        )
    elif backend == "R2":
        if r2_store is None:
            raise ValueError("r2_store is required for R2 state backend")
        state_result = FinalizerStateWriter.persist_r2(
            projected,
            store=r2_store,
            observed_at=observed_at,
            run_id=run_id,
            allow_bootstrap=allow_bootstrap,
        )
    else:
        raise ValueError(f"Unsupported state backend: {state_backend}")

    sync_state_annotations(records, projected)
    state_ids = {
        str(((record.get("raw_extra") or {}).get("state") or {}).get("state_id") or "")
        for record in records
    }
    state_ids.discard("")
    projection_summary = dict(projection_summary)
    projection_summary["unique_state_ids_observed"] = len(state_ids)
    projection_summary["state_id_cardinality_matches_records"] = len(state_ids) == len(records)
    if len(state_ids) != len(records):
        raise RuntimeError(
            f"Stage 10 state identity collision: {len(records)} canonical records mapped to {len(state_ids)} state IDs"
        )
    return state_result, projection_summary


def _present_shards(*, run_id: str, artifact_root: Path) -> set[str]:
    run_dir = artifact_root / run_id / "shards"
    if not run_dir.exists():
        return set()
    return {path.parent.name for path in run_dir.glob("*/manifest.json")}


def collect_source_diagnostics(*, run_id: str, artifact_root: Path) -> dict[str, dict[str, Any]]:
    run_dir = artifact_root / run_id / "shards"
    aggregated: dict[str, dict[str, Any]] = {}

    def merge(key: str, *, status: str, records: int = 0, error: str = "", warnings: list[str] | None = None) -> None:
        row = aggregated.setdefault(key, {"status": "UNKNOWN", "records": 0, "errors": [], "warnings": []})
        row["records"] += int(records or 0)
        if error and error not in row["errors"]:
            row["errors"].append(error)
        for warning in warnings or []:
            if warning and warning not in row["warnings"]:
                row["warnings"].append(warning)
        statuses = set(row.setdefault("_statuses", []))
        statuses.add(str(status or "UNKNOWN").upper())
        row["_statuses"] = sorted(statuses)

    for shard_dir in sorted(run_dir.glob("*")) if run_dir.exists() else []:
        if not (shard_dir / "manifest.json").exists():
            continue
        try:
            manifest, records, diagnostics = verify_shard_bundle(shard_dir)
            source_results = (diagnostics.get("metadata") or {}).get("source_results") or []
            if source_results:
                for item in source_results:
                    merge(
                        str(item.get("report_key") or item.get("source_id") or "unknown"),
                        status=str(item.get("status") or manifest.status.value),
                        records=int(item.get("records") or 0),
                        error=str(item.get("error") or ""),
                        warnings=list(item.get("warnings") or []),
                    )
            else:
                for source_id in manifest.source_ids:
                    matching = sum(
                        1
                        for record in records
                        if str((record.get("source") or {}).get("source_key") or "") == source_id
                    )
                    merge(
                        source_id,
                        status=manifest.status.value,
                        records=matching,
                        warnings=list(diagnostics.get("warnings") or []),
                        error="; ".join(diagnostics.get("errors") or []),
                    )
        except Exception as exc:
            merge(shard_dir.name, status="ERROR", error=f"{type(exc).__name__}: {exc}")

    output: dict[str, dict[str, Any]] = {}
    for key, row in aggregated.items():
        statuses = set(row.pop("_statuses", []))
        if statuses == {"OK"}:
            status = "OK"
        elif "OK" in statuses or "PARTIAL" in statuses:
            status = "PARTIAL"
        elif "ERROR" in statuses:
            status = "ERROR"
        else:
            status = "UNKNOWN"
        output[key] = {
            "status": status,
            "records": row["records"],
            "error": "; ".join(row["errors"]),
            "warnings": row["warnings"],
        }
    return output


def _load_fanin_records(*, run_id: str, output_root: Path) -> list[dict[str, Any]]:
    path = output_root / run_id / "finalizer" / "records.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("Stage 4 finalizer records payload is not a list")
    return data


def run_preprod_finalization(
    *,
    run_id: str,
    artifact_root: Path,
    output_root: Path,
    observed_at: str,
    state_backend: str,
    state_path: Path | None = None,
    r2_store: R2StateStore | None = None,
    allow_bootstrap: bool = False,
    expected_shards: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Run the Stage 10 central path after immutable shards have finished."""
    present_shards = _present_shards(run_id=run_id, artifact_root=artifact_root)
    expected = list(dict.fromkeys(expected_shards or []))
    missing_shards = [shard for shard in expected if shard not in present_shards]

    fanin = finalize_run(run_id=run_id, artifact_root=artifact_root, output_root=output_root)
    source_diagnostics = collect_source_diagnostics(run_id=run_id, artifact_root=artifact_root)
    for shard in missing_shards:
        source_diagnostics[f"shard::{shard}"] = {
            "status": "ERROR",
            "records": 0,
            "error": "MISSING_SHARD_ARTIFACT",
            "warnings": ["Expected Stage 10 shard artifact was not published; no closure is inferred from its absence."],
        }
    degraded_sources = sorted(
        key
        for key, item in source_diagnostics.items()
        if str(item.get("status") or "UNKNOWN").upper() in {"ERROR", "PARTIAL"}
    )
    preprod_dir = output_root / run_id / "preprod"

    if fanin.status.value == "ERROR":
        summary = {
            "contract_version": PREPROD_CONTRACT_VERSION,
            "run_id": run_id,
            "status": "ERROR",
            "fanin": fanin.to_dict(),
            "expected_shards": expected,
            "present_shards": sorted(present_shards),
            "missing_shards": missing_shards,
            "degraded_sources": degraded_sources,
            "state_write": "SKIPPED_NO_ACCEPTED_SHARDS",
            "reporting": "SKIPPED_NO_ACCEPTED_SHARDS",
            "source_diagnostics": source_diagnostics,
        }
        atomic_create_bytes(preprod_dir / "preprod_summary.json", _json_bytes(summary))
        return summary

    raw_records = _load_fanin_records(run_id=run_id, output_root=output_root)
    canonical, canonical_summary = canonicalize_records(raw_records)
    for record in canonical:
        apply_central_availability(record, observed_at=observed_at)
    evaluate_canonical_records(canonical)
    _validate_canonical(canonical)

    state_result, state_projection = persist_preprod_state(
        canonical,
        state_backend=state_backend,
        observed_at=observed_at,
        run_id=run_id,
        state_path=state_path,
        r2_store=r2_store,
        allow_bootstrap=allow_bootstrap,
    )

    payload = build_reporting_payload(
        canonical,
        run_id=run_id,
        generated_at=observed_at,
        state_summary=state_result.summary,
        source_diagnostics=source_diagnostics,
    )
    report_path = build_xlsx(payload, preprod_dir / "academic_job_report.xlsx")
    report_summary_path = write_summary_json(payload, preprod_dir / "report_summary.json")

    if state_result.summary.get("records_observed") != len(canonical):
        raise RuntimeError("State/report integration mismatch: state records_observed != canonical records")
    if len(payload["audit"]) != len(canonical):
        raise RuntimeError("State/report integration mismatch: report AUDIT != canonical records")
    if int(state_result.summary.get("not_observed_inferred_closed") or 0) != 0:
        raise RuntimeError("Fail-open invariant violated: absence inferred closure")

    final_status = "PASS" if fanin.status.value == "OK" and not missing_shards and not degraded_sources else "PARTIAL_PASS"
    summary = {
        "contract_version": PREPROD_CONTRACT_VERSION,
        "run_id": run_id,
        "status": final_status,
        "fanin": fanin.to_dict(),
        "expected_shards": expected,
        "present_shards": sorted(present_shards),
        "missing_shards": missing_shards,
        "degraded_sources": degraded_sources,
        "canonicalization": canonical_summary,
        "evaluated_records": len(canonical),
        "state_identity_projection": state_projection,
        "state": state_result.summary,
        "persistence": state_result.persistence,
        "reporting": payload["summary"],
        "source_diagnostics": source_diagnostics,
        "consistency": {
            "raw_to_canonical_nonexpanding": len(canonical) <= len(raw_records),
            "evaluation_count_matches_canonical": len(canonical) == len(payload["audit"]),
            "state_observed_matches_canonical": state_result.summary.get("records_observed") == len(canonical),
            "state_id_cardinality_matches_canonical": state_projection.get("state_id_cardinality_matches_records") is True,
            "absence_inferred_closed": int(state_result.summary.get("not_observed_inferred_closed") or 0),
            "missing_shards_surface_as_partial": not missing_shards or final_status == "PARTIAL_PASS",
            "source_degradation_surfaces_as_partial": not degraded_sources or final_status == "PARTIAL_PASS",
        },
        "artifacts": {
            "report": str(report_path),
            "report_summary": str(report_summary_path),
            "canonical_records": str(preprod_dir / "canonical_records.json"),
            "source_diagnostics": str(preprod_dir / "source_diagnostics.json"),
        },
    }
    atomic_create_bytes(preprod_dir / "canonical_records.json", _json_bytes(canonical))
    atomic_create_bytes(preprod_dir / "source_diagnostics.json", _json_bytes(source_diagnostics))
    atomic_create_bytes(preprod_dir / "preprod_summary.json", _json_bytes(summary))
    return summary
