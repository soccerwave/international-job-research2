from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable

from src.llm.dual_path_routing import DualPathRoutingResult
from src.llm.full_evaluation_routing import FullEvaluationRecord, FullReviewCandidate
from src.llm.rescue_triage import CLEARLY_OUT_OF_SCOPE
from src.llm.shadow_evaluator import ShadowEvaluationError, ShadowEvaluator

ORIGIN_RESCUE_REJECT_AUDIT = "RESCUE_REJECT_AUDIT"
DEFAULT_AUDIT_SAMPLE_SIZE = 10


@dataclass(frozen=True)
class RescueRejectAuditSelection:
    candidates: tuple[FullReviewCandidate, ...]
    population_size: int
    requested_sample_size: int


@dataclass(frozen=True)
class RescueRejectAuditRun:
    records: tuple[FullEvaluationRecord, ...]
    failures: tuple[dict[str, str], ...]


def _decision(record: dict[str, Any]) -> str:
    result = record.get("llm_result")
    if not isinstance(result, dict):
        return ""
    return str(result.get("decision") or "").strip().upper()


def _triage_id(record: dict[str, Any]) -> str | None:
    value = str(record.get("triage_id") or "").strip()
    return value or None


def select_rescue_reject_audit_candidates(
    routing: DualPathRoutingResult,
    *,
    rescue_triage_records: Iterable[dict[str, Any]],
    run_id: str,
    sample_size: int = DEFAULT_AUDIT_SAMPLE_SIZE,
) -> RescueRejectAuditSelection:
    if sample_size < 0:
        raise ValueError("sample_size must be non-negative")

    triage = {
        str(row.get("job_id") or "").strip(): row
        for row in rescue_triage_records
        if str(row.get("job_id") or "").strip()
    }

    population: list[FullReviewCandidate] = []
    for routed in routing.rescue_triage:
        record = triage.get(routed.job_id)
        if record is None or _decision(record) != CLEARLY_OUT_OF_SCOPE:
            continue
        population.append(
            FullReviewCandidate(
                job_id=routed.job_id,
                origin=ORIGIN_RESCUE_REJECT_AUDIT,
                job=routed.job,
                triage_id=_triage_id(record),
            )
        )

    def rank(candidate: FullReviewCandidate) -> str:
        material = f"{run_id}\0{candidate.job_id}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    population.sort(key=rank)
    chosen = tuple(population[: min(sample_size, len(population))])
    return RescueRejectAuditSelection(
        candidates=chosen,
        population_size=len(population),
        requested_sample_size=sample_size,
    )


def run_rescue_reject_audit(
    selection: RescueRejectAuditSelection,
    *,
    evaluator: ShadowEvaluator,
) -> RescueRejectAuditRun:
    records: list[FullEvaluationRecord] = []
    failures: list[dict[str, str]] = []

    for candidate in selection.candidates:
        try:
            evaluation = evaluator.evaluate(candidate.job)
        except ShadowEvaluationError as exc:
            failures.append(
                {
                    "job_id": candidate.job_id,
                    "origin": ORIGIN_RESCUE_REJECT_AUDIT,
                    "error": str(exc),
                }
            )
            continue

        records.append(
            FullEvaluationRecord(
                job_id=candidate.job_id,
                origin=ORIGIN_RESCUE_REJECT_AUDIT,
                triage_id=candidate.triage_id,
                evaluation=evaluation,
            )
        )

    return RescueRejectAuditRun(
        records=tuple(records),
        failures=tuple(failures),
    )


def rescue_reject_audit_summary(
    selection: RescueRejectAuditSelection,
    run: RescueRejectAuditRun,
) -> dict[str, Any]:
    favorable = {"STRONG_APPLY", "APPLY", "REVIEW"}
    favorable_count = 0
    cache_hits = 0
    api_evaluations = 0

    for row in run.records:
        result = row.evaluation.get("llm_result") if isinstance(row.evaluation, dict) else None
        decision = str((result or {}).get("decision") or "").upper()
        if decision in favorable:
            favorable_count += 1
        if row.evaluation.get("cache_hit") is True:
            cache_hits += 1
        else:
            api_evaluations += 1

    return {
        "population_size": selection.population_size,
        "requested_sample_size": selection.requested_sample_size,
        "selected_sample_size": len(selection.candidates),
        "completed": len(run.records),
        "failed": len(run.failures),
        "favorable_full_reviews": favorable_count,
        "cache_hits": cache_hits,
        "api_evaluations": api_evaluations,
    }
