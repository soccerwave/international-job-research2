from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable


POSITIVE_RECOMMENDATIONS = {"STRONG_APPLY", "APPLY"}
REVIEW_RECOMMENDATIONS = {"REVIEW"}
NEGATIVE_RECOMMENDATIONS = {"LOW_PRIORITY", "SKIP"}
GOOD_DETAIL = {"FULL", "PARTIAL"}


@dataclass(frozen=True)
class SamplingConfig:
    review_target: int = 250
    negative_target: int = 150
    targeted_negative_fraction: float = 0.5

    def __post_init__(self) -> None:
        if self.review_target < 0 or self.negative_target < 0:
            raise ValueError("sampling targets must be non-negative")
        if not 0.0 <= self.targeted_negative_fraction <= 1.0:
            raise ValueError("targeted_negative_fraction must be between 0 and 1")


@dataclass(frozen=True)
class SampledJob:
    job: dict[str, Any]
    sampling_bucket: str
    selection_rank: str


def _job_id(job: dict[str, Any]) -> str:
    return str(job.get("canonical_id") or job.get("source_record_id") or "").strip()


def _evaluation(job: dict[str, Any]) -> dict[str, Any]:
    raw = job.get("raw_extra") or {}
    evaluation = raw.get("evaluation")
    return evaluation if isinstance(evaluation, dict) else {}


def _recommendation(job: dict[str, Any]) -> str:
    return str(_evaluation(job).get("recommendation") or "").upper()


def _detail_status(job: dict[str, Any]) -> str:
    return str((job.get("description") or {}).get("detail_status") or "UNKNOWN").upper()


def _source_key(job: dict[str, Any]) -> str:
    return str((job.get("source") or {}).get("source_key") or "UNKNOWN").strip() or "UNKNOWN"


def _country(job: dict[str, Any]) -> str:
    loc = job.get("location") or {}
    return str(loc.get("country_code") or loc.get("country_name") or "UNKNOWN").upper().strip() or "UNKNOWN"


def _stable_rank(job: dict[str, Any], *, seed: str, bucket: str) -> str:
    job_id = _job_id(job)
    if not job_id:
        raise ValueError("cannot sample job without stable identifier")
    material = f"{seed}|{bucket}|{job_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _stratum(job: dict[str, Any]) -> tuple[str, str]:
    return _country(job), _source_key(job)


def _round_robin_stratified(
    jobs: Iterable[dict[str, Any]],
    *,
    target: int,
    seed: str,
    bucket: str,
) -> list[SampledJob]:
    if target <= 0:
        return []

    strata: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
    for job in jobs:
        rank = _stable_rank(job, seed=seed, bucket=bucket)
        strata.setdefault(_stratum(job), []).append((rank, job))

    for rows in strata.values():
        rows.sort(key=lambda item: item[0])

    ordered_strata = sorted(
        strata,
        key=lambda key: hashlib.sha256(f"{seed}|{bucket}|{key[0]}|{key[1]}".encode("utf-8")).hexdigest(),
    )

    selected: list[SampledJob] = []
    index = 0
    while len(selected) < target:
        progressed = False
        for key in ordered_strata:
            rows = strata[key]
            if index >= len(rows):
                continue
            rank, job = rows[index]
            selected.append(SampledJob(job=job, sampling_bucket=bucket, selection_rank=rank))
            progressed = True
            if len(selected) >= target:
                break
        if not progressed:
            break
        index += 1
    return selected


def _is_targeted_negative(job: dict[str, Any]) -> bool:
    if _recommendation(job) not in NEGATIVE_RECOMMENDATIONS:
        return False
    if _detail_status(job) not in GOOD_DETAIL:
        return False

    evaluation = _evaluation(job)
    blocker_codes = evaluation.get("blocker_codes") or []
    if blocker_codes:
        return False

    role_status = str(evaluation.get("role_policy_status") or "").upper()
    review_codes = evaluation.get("review_codes") or []
    dimensions = evaluation.get("dimensions") if isinstance(evaluation.get("dimensions"), dict) else {}
    scientific = str(dimensions.get("scientific") or "").upper()
    level = str(dimensions.get("level") or "").upper()
    methods = str(dimensions.get("methods") or "").upper()

    return bool(
        review_codes
        or role_status in {"AMBIGUOUS", "CONDITIONAL", "PRIMARY", "SECONDARY"}
        or scientific in {"ADJACENT", "GOOD", "UNCLEAR"}
        or level in {"REVIEW", "UNKNOWN", "ACCEPTABLE"}
        or methods in {"REVIEW", "UNKNOWN", "TRANSFERABLE", "ACCEPTABLE"}
    )


def _dedupe_jobs(jobs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for job in jobs:
        job_id = _job_id(job)
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        out.append(job)
    return out


def select_shadow_sample(
    jobs: Iterable[dict[str, Any]],
    *,
    seed: str,
    config: SamplingConfig = SamplingConfig(),
    review_more_job_ids: set[str] | None = None,
) -> list[SampledJob]:
    """Select jobs for shadow LLM evaluation without changing their LLM context.

    The deterministic evaluator may influence *which* jobs are sampled, but its outputs
    are not copied into the LLM input. All STRONG_APPLY/APPLY jobs are retained even if
    that makes the daily total exceed nominal sampling targets.
    """

    rows = _dedupe_jobs(jobs)
    review_more_job_ids = set(review_more_job_ids or set())

    positives: list[SampledJob] = []
    for job in rows:
        if _recommendation(job) in POSITIVE_RECOMMENDATIONS:
            positives.append(
                SampledJob(
                    job=job,
                    sampling_bucket="ALL_POSITIVE",
                    selection_rank=_stable_rank(job, seed=seed, bucket="ALL_POSITIVE"),
                )
            )
    positives.sort(key=lambda row: row.selection_rank)
    positive_ids = {_job_id(row.job) for row in positives}

    review_pool = [
        job
        for job in rows
        if _job_id(job) not in positive_ids
        and (_recommendation(job) in REVIEW_RECOMMENDATIONS or _job_id(job) in review_more_job_ids)
    ]
    reviews = _round_robin_stratified(
        review_pool,
        target=config.review_target,
        seed=seed,
        bucket="REVIEW_STRATIFIED",
    )
    selected_ids = positive_ids | {_job_id(row.job) for row in reviews}

    negative_pool = [
        job
        for job in rows
        if _job_id(job) not in selected_ids
        and _recommendation(job) in NEGATIVE_RECOMMENDATIONS
        and _detail_status(job) in GOOD_DETAIL
    ]

    targeted_target = round(config.negative_target * config.targeted_negative_fraction)
    blind_target = config.negative_target - targeted_target

    targeted_pool = [job for job in negative_pool if _is_targeted_negative(job)]
    targeted = _round_robin_stratified(
        targeted_pool,
        target=targeted_target,
        seed=seed,
        bucket="NEGATIVE_TARGETED",
    )
    targeted_ids = {_job_id(row.job) for row in targeted}

    # Blind exploration deliberately ignores scientific fit dimensions and review codes.
    # Its purpose is to expose rule-evaluator blind spots rather than reproduce them.
    blind_pool = [job for job in negative_pool if _job_id(job) not in targeted_ids]
    blind = _round_robin_stratified(
        blind_pool,
        target=blind_target,
        seed=seed,
        bucket="NEGATIVE_BLIND_EXPLORATION",
    )

    return positives + reviews + targeted + blind


def sampling_summary(sample: Iterable[SampledJob]) -> dict[str, Any]:
    rows = list(sample)
    by_bucket: dict[str, int] = {}
    by_recommendation: dict[str, int] = {}
    for row in rows:
        by_bucket[row.sampling_bucket] = by_bucket.get(row.sampling_bucket, 0) + 1
        recommendation = _recommendation(row.job) or "UNKNOWN"
        by_recommendation[recommendation] = by_recommendation.get(recommendation, 0) + 1
    return {
        "selected": len(rows),
        "by_bucket": dict(sorted(by_bucket.items())),
        "by_rule_recommendation": dict(sorted(by_recommendation.items())),
    }
