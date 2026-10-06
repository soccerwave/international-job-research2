from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

MAIN_FULL_REVIEW = "MAIN_FULL_REVIEW"
RESCUE_TRIAGE = "RESCUE_TRIAGE"


def _job_id(job: dict[str, Any]) -> str:
    return str(job.get("canonical_id") or job.get("source_record_id") or "").strip()


def _clean_ids(values: Iterable[str]) -> set[str]:
    return {str(value).strip() for value in values if str(value).strip()}


@dataclass(frozen=True)
class RoutedJob:
    job_id: str
    route: str
    job: dict[str, Any]


@dataclass(frozen=True)
class DualPathRoutingResult:
    main_full_review: tuple[RoutedJob, ...]
    rescue_triage: tuple[RoutedJob, ...]
    missing_main_ids: tuple[str, ...]
    missing_rescue_ids: tuple[str, ...]

    @property
    def selected_job_ids(self) -> frozenset[str]:
        return frozenset(
            row.job_id
            for row in (*self.main_full_review, *self.rescue_triage)
        )


def route_dual_path_candidates(
    jobs: Iterable[dict[str, Any]],
    *,
    main_job_ids: Iterable[str],
    rescue_candidate_job_ids: Iterable[str],
) -> DualPathRoutingResult:
    """Route canonical jobs into the L6.2 MAIN and Rescue paths.

    This function intentionally performs no semantic triage and no LLM
    evaluation. MAIN membership is authoritative for routing precedence.
    Rescue candidates that overlap MAIN are removed from Rescue so one job
    cannot enter both paths.

    Seen/change status is deliberately ignored. On a cold start, every MAIN
    job can be routed for evaluation. On later runs, the evaluation cache is
    responsible for suppressing unchanged API work.
    """

    main_ids = _clean_ids(main_job_ids)
    rescue_ids = _clean_ids(rescue_candidate_job_ids) - main_ids

    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for job in jobs:
        job_id = _job_id(job)
        if not job_id or job_id in by_id:
            continue
        by_id[job_id] = job
        order.append(job_id)

    main_rows: list[RoutedJob] = []
    rescue_rows: list[RoutedJob] = []
    for job_id in order:
        job = by_id[job_id]
        if job_id in main_ids:
            main_rows.append(RoutedJob(job_id=job_id, route=MAIN_FULL_REVIEW, job=job))
        elif job_id in rescue_ids:
            rescue_rows.append(RoutedJob(job_id=job_id, route=RESCUE_TRIAGE, job=job))

    available = set(by_id)
    missing_main = tuple(sorted(main_ids - available))
    missing_rescue = tuple(sorted(rescue_ids - available))

    return DualPathRoutingResult(
        main_full_review=tuple(main_rows),
        rescue_triage=tuple(rescue_rows),
        missing_main_ids=missing_main,
        missing_rescue_ids=missing_rescue,
    )


def routing_summary(result: DualPathRoutingResult) -> dict[str, Any]:
    return {
        "main_full_review": len(result.main_full_review),
        "rescue_triage": len(result.rescue_triage),
        "selected_total": len(result.selected_job_ids),
        "missing_main_ids": list(result.missing_main_ids),
        "missing_rescue_ids": list(result.missing_rescue_ids),
    }
