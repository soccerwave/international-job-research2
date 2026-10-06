from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from src.llm.dual_path_routing import DualPathRoutingResult, RoutedJob
from src.llm.rescue_triage import PASS_TO_FULL_REVIEW
from src.llm.shadow_evaluator import ShadowEvaluationError, ShadowEvaluator

ORIGIN_MAIN = "MAIN"
ORIGIN_LLM_RESCUE = "LLM_RESCUE"


@dataclass(frozen=True)
class FullReviewCandidate:
    job_id: str
    origin: str
    job: dict[str, Any]
    triage_id: str | None = None


@dataclass(frozen=True)
class FullReviewSelection:
    candidates: tuple[FullReviewCandidate, ...]
    rescue_rejected_ids: tuple[str, ...]
    rescue_missing_triage_ids: tuple[str, ...]


@dataclass(frozen=True)
class FullEvaluationRecord:
    job_id: str
    origin: str
    triage_id: str | None
    evaluation: dict[str, Any]


@dataclass(frozen=True)
class FullEvaluationRun:
    records: tuple[FullEvaluationRecord, ...]
    failures: tuple[dict[str, str], ...]


def _triage_by_job_id(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in records:
        job_id = str(row.get("job_id") or "").strip()
        if not job_id:
            continue
        out[job_id] = row
    return out


def _triage_decision(record: dict[str, Any]) -> str:
    result = record.get("llm_result")
    if not isinstance(result, dict):
        return ""
    return str(result.get("decision") or "").strip().upper()


def _triage_id(record: dict[str, Any]) -> str | None:
    value = str(record.get("triage_id") or "").strip()
    return value or None


def select_full_review_candidates(
    routing: DualPathRoutingResult,
    *,
    rescue_triage_records: Iterable[dict[str, Any]],
) -> FullReviewSelection:
    """Select jobs that proceed to independent Full-JD LLM evaluation.

    MAIN jobs always proceed. Rescue jobs proceed only when their cheap L7
    triage result is PASS_TO_FULL_REVIEW. Triage decisions and rule outputs are
    routing metadata only and are not injected into the canonical job.
    """

    triage = _triage_by_job_id(rescue_triage_records)

    candidates: list[FullReviewCandidate] = [
        FullReviewCandidate(
            job_id=row.job_id,
            origin=ORIGIN_MAIN,
            job=row.job,
            triage_id=None,
        )
        for row in routing.main_full_review
    ]

    rejected: list[str] = []
    missing: list[str] = []
    for row in routing.rescue_triage:
        triage_record = triage.get(row.job_id)
        if triage_record is None:
            missing.append(row.job_id)
            continue
        if _triage_decision(triage_record) == PASS_TO_FULL_REVIEW:
            candidates.append(
                FullReviewCandidate(
                    job_id=row.job_id,
                    origin=ORIGIN_LLM_RESCUE,
                    job=row.job,
                    triage_id=_triage_id(triage_record),
                )
            )
        else:
            rejected.append(row.job_id)

    return FullReviewSelection(
        candidates=tuple(candidates),
        rescue_rejected_ids=tuple(sorted(rejected)),
        rescue_missing_triage_ids=tuple(sorted(missing)),
    )


def run_full_evaluations(
    selection: FullReviewSelection,
    *,
    evaluator: ShadowEvaluator,
) -> FullEvaluationRun:
    """Run the existing independent Full-JD evaluator on selected candidates.

    Provenance is attached only after evaluator.evaluate(job) returns, so the
    evaluator prompt cannot be anchored by MAIN/Rescue route information.
    """

    records: list[FullEvaluationRecord] = []
    failures: list[dict[str, str]] = []

    for candidate in selection.candidates:
        try:
            evaluation = evaluator.evaluate(candidate.job)
        except ShadowEvaluationError as exc:
            failures.append(
                {
                    "job_id": candidate.job_id,
                    "origin": candidate.origin,
                    "error": str(exc),
                }
            )
            continue

        records.append(
            FullEvaluationRecord(
                job_id=candidate.job_id,
                origin=candidate.origin,
                triage_id=candidate.triage_id,
                evaluation=evaluation,
            )
        )

    return FullEvaluationRun(
        records=tuple(records),
        failures=tuple(failures),
    )


def full_evaluation_summary(
    selection: FullReviewSelection,
    run: FullEvaluationRun,
) -> dict[str, Any]:
    by_origin = {ORIGIN_MAIN: 0, ORIGIN_LLM_RESCUE: 0}
    cache_hits = 0
    api_evaluations = 0

    for row in run.records:
        by_origin[row.origin] = by_origin.get(row.origin, 0) + 1
        if row.evaluation.get("cache_hit") is True:
            cache_hits += 1
        else:
            api_evaluations += 1

    return {
        "selected_full_review": len(selection.candidates),
        "selected_main": sum(1 for row in selection.candidates if row.origin == ORIGIN_MAIN),
        "selected_rescue": sum(1 for row in selection.candidates if row.origin == ORIGIN_LLM_RESCUE),
        "rescue_rejected": len(selection.rescue_rejected_ids),
        "rescue_missing_triage": len(selection.rescue_missing_triage_ids),
        "completed": len(run.records),
        "failed": len(run.failures),
        "completed_by_origin": by_origin,
        "cache_hits": cache_hits,
        "api_evaluations": api_evaluations,
    }
