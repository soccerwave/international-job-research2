from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from src.state.r2_store import R2StateStore

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_SCHEMA_PATH = ROOT / "schemas" / "llm_experiment_evidence.schema.json"
SCHEMA_VERSION = "LLM_EXPERIMENT_EVIDENCE_V0.1"
DEFAULT_PREFIX = "llm/experiments"


class ExperimentEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class PersistedExperimentEvidence:
    key: str
    sha256: str
    bytes: int
    etag: str | None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_segment(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.-")
    return cleaned or fallback


def _load_schema() -> dict[str, Any]:
    return json.loads(EVIDENCE_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(bundle: dict[str, Any]) -> None:
    validator = Draft202012Validator(_load_schema())
    errors = sorted(validator.iter_errors(bundle), key=lambda e: list(e.path))
    if errors:
        raise ExperimentEvidenceError(
            "invalid experiment evidence bundle: " + "; ".join(error.message for error in errors)
        )


def _rule_eval(job: dict[str, Any]) -> dict[str, Any]:
    top = job.get("evaluation")
    if isinstance(top, dict):
        return top
    raw = job.get("raw_extra") or {}
    nested = raw.get("evaluation")
    return nested if isinstance(nested, dict) else {}


def _job_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    position = job.get("position") or {}
    location = job.get("location") or {}
    description = job.get("description") or {}
    full_jd = str(description.get("full_jd") or "")
    return {
        "job_id": str(job.get("canonical_id") or job.get("source_record_id") or "").strip(),
        "title": _clean(position.get("title_raw") or position.get("title_normalized")),
        "institution": _clean(position.get("institution_raw") or position.get("institution_normalized")),
        "country": location.get("country_name") or location.get("country_code"),
        "source_url": (
            (job.get("source") or {}).get("detail_url")
            or (job.get("source") or {}).get("listing_url")
            or (job.get("source") or {}).get("apply_url")
        ),
        "detail_status": str(description.get("detail_status") or "UNKNOWN").upper(),
        "full_jd_sha256": hashlib.sha256(full_jd.encode("utf-8")).hexdigest() if full_jd else None,
    }


def _full_eval_evidence(
    job: dict[str, Any],
    full_record: Any,
    *,
    origin: str,
) -> dict[str, Any]:
    evaluation = full_record.evaluation if hasattr(full_record, "evaluation") else {}
    evaluation = evaluation if isinstance(evaluation, dict) else {}
    result = evaluation.get("llm_result")
    result = result if isinstance(result, dict) else {}
    rule = _rule_eval(job)
    return {
        **_job_snapshot(job),
        "origin": origin,
        "triage_id": getattr(full_record, "triage_id", None),
        "rule_recommendation": str(rule.get("recommendation") or "").upper() or None,
        "rule_evaluator_version": rule.get("evaluator_version"),
        "evaluation_id": evaluation.get("evaluation_id"),
        "llm_decision": str(result.get("decision") or "").upper() or None,
        "llm_fit_score": result.get("fit_score"),
        "llm_confidence": result.get("confidence"),
        "evidence_quality": result.get("evidence_quality"),
        "hard_blocker": result.get("hard_blocker"),
        "hard_blocker_reason": result.get("hard_blocker_reason"),
        "reason_short": result.get("reason_short"),
        "cache_hit": bool(evaluation.get("cache_hit")),
        "cache_fingerprint": evaluation.get("cache_fingerprint"),
        "model": evaluation.get("model"),
        "input_tokens": evaluation.get("input_tokens"),
        "output_tokens": evaluation.get("output_tokens"),
        "latency_ms": evaluation.get("latency_ms"),
        "evaluated_at": evaluation.get("evaluated_at"),
    }


def _triage_evidence(record: dict[str, Any]) -> dict[str, Any]:
    result = record.get("llm_result")
    result = result if isinstance(result, dict) else {}
    return {
        "job_id": record.get("job_id"),
        "triage_id": record.get("triage_id"),
        "decision": result.get("decision"),
        "reason_short": result.get("reason_short"),
        "cache_hit": bool(record.get("cache_hit")),
        "cache_fingerprint": record.get("cache_fingerprint"),
        "model": record.get("model"),
        "input_tokens": record.get("input_tokens"),
        "output_tokens": record.get("output_tokens"),
        "latency_ms": record.get("latency_ms"),
        "evaluated_at": record.get("evaluated_at"),
    }


def build_experiment_evidence_bundle(
    *,
    run_id: str,
    run_date: str,
    model: str,
    candidate_profile_version: str,
    canonical_jobs: Iterable[dict[str, Any]],
    full_evaluation_records: Iterable[Any],
    rescue_triage_records: Iterable[dict[str, Any]],
    disagreement_rows: Iterable[dict[str, Any]],
    failures: Iterable[dict[str, Any]],
    rescue_reject_audit_records: Iterable[Any] = (),
    extra_summary: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    jobs = {
        str(job.get("canonical_id") or job.get("source_record_id") or "").strip(): job
        for job in canonical_jobs
        if str(job.get("canonical_id") or job.get("source_record_id") or "").strip()
    }

    main: list[dict[str, Any]] = []
    rescue_full: list[dict[str, Any]] = []
    full_rows = list(full_evaluation_records)
    for row in full_rows:
        job_id = str(getattr(row, "job_id", "") or "").strip()
        job = jobs.get(job_id)
        if job is None:
            raise ExperimentEvidenceError(f"full evaluation has no canonical job: {job_id or '<missing>'}")
        origin = str(getattr(row, "origin", "") or "").strip()
        evidence = _full_eval_evidence(job, row, origin=origin)
        if origin == "MAIN":
            main.append(evidence)
        elif origin == "LLM_RESCUE":
            rescue_full.append(evidence)
        else:
            raise ExperimentEvidenceError(f"unsupported full evaluation origin: {origin or '<missing>'}")

    triage_rows = [_triage_evidence(row) for row in rescue_triage_records]
    audit_rows: list[dict[str, Any]] = []
    for row in rescue_reject_audit_records:
        job_id = str(getattr(row, "job_id", "") or "").strip()
        job = jobs.get(job_id)
        if job is None:
            raise ExperimentEvidenceError(
                f"Rescue reject audit evaluation has no canonical job: {job_id or '<missing>'}"
            )
        audit_rows.append(_full_eval_evidence(job, row, origin="RESCUE_REJECT_AUDIT"))

    disagreement_list = [dict(row) for row in disagreement_rows]
    failure_list = [dict(row) for row in failures]

    metered_rows = main + rescue_full + triage_rows + audit_rows
    input_tokens = sum(int(row.get("input_tokens") or 0) for row in metered_rows)
    output_tokens = sum(int(row.get("output_tokens") or 0) for row in metered_rows)
    api_calls = sum(1 for row in metered_rows if not row.get("cache_hit"))
    cache_hits = sum(1 for row in metered_rows if row.get("cache_hit"))

    summary: dict[str, Any] = {
        "main_full_evaluations": len(main),
        "rescue_triage_evaluations": len(triage_rows),
        "rescue_full_evaluations": len(rescue_full),
        "rescue_reject_audit_evaluations": len(audit_rows),
        "disagreements": len(disagreement_list),
        "failures": len(failure_list),
        "cache_hits": cache_hits,
        "api_calls": api_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if extra_summary:
        summary.update(extra_summary)

    bundle = {
        "schema_version": SCHEMA_VERSION,
        "run_id": _clean(run_id),
        "run_date": _clean(run_date),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "model": _clean(model),
        "candidate_profile_version": _clean(candidate_profile_version),
        "summary": summary,
        "main_evaluations": main,
        "rescue_triage": triage_rows,
        "rescue_full_evaluations": rescue_full,
        "rescue_reject_audit": audit_rows,
        "disagreements": disagreement_list,
        "failures": failure_list,
    }
    _validate(bundle)
    return bundle


def serialize_experiment_evidence(bundle: dict[str, Any]) -> bytes:
    _validate(bundle)
    return (
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


class R2ExperimentEvidenceStore:
    """Immutable per-run evidence bundles for the two-week shadow experiment."""

    def __init__(self, state_store: R2StateStore, *, prefix: str = DEFAULT_PREFIX) -> None:
        self.state_store = state_store
        self.prefix = str(prefix or "").strip("/")
        if not self.prefix:
            raise ValueError("experiment evidence prefix is required")

    @classmethod
    def from_env(cls) -> "R2ExperimentEvidenceStore":
        return cls(R2StateStore.from_env())

    def key_for(self, *, run_date: str, run_id: str) -> str:
        date = _safe_segment(run_date, "unknown-date")
        safe_run = _safe_segment(run_id, "run")
        return self.state_store.key(f"{self.prefix}/{date}/{safe_run}/evidence.json")

    def persist(self, bundle: dict[str, Any]) -> PersistedExperimentEvidence:
        payload = serialize_experiment_evidence(bundle)
        digest = hashlib.sha256(payload).hexdigest()
        key = self.key_for(run_date=bundle["run_date"], run_id=bundle["run_id"])
        kwargs = {
            "Bucket": self.state_store.bucket,
            "Key": key,
            "Body": payload,
            "ContentType": "application/json",
            "Metadata": {
                "sha256": digest,
                "schema-version": SCHEMA_VERSION,
                "run-id": _safe_segment(bundle["run_id"], "run"),
                "run-date": bundle["run_date"],
            },
            "custom_headers": {"If-None-Match": "*"},
        }
        try:
            response = self.state_store.client.put_object(**kwargs)
        except Exception as exc:
            code = ""
            response_obj = getattr(exc, "response", None)
            if isinstance(response_obj, dict):
                error = response_obj.get("Error") or {}
                code = str(error.get("Code") or response_obj.get("ResponseMetadata", {}).get("HTTPStatusCode") or "")
            if code in {"412", "PreconditionFailed", "ConditionalRequestConflict"}:
                raise ExperimentEvidenceError(
                    f"experiment evidence already exists for run_id={bundle['run_id']}; refusing overwrite"
                ) from exc
            raise
        return PersistedExperimentEvidence(
            key=key,
            sha256=digest,
            bytes=len(payload),
            etag=str(response.get("ETag") or "").strip() or None,
        )
