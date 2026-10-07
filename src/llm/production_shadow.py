from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from src.evaluation.calibrated_e021 import evaluate_calibrated
from src.evaluation.negative_shadow_tier1 import evaluate_negative_shadow
from src.evaluation.tier2_shadow import evaluate_tier2_shadow
from src.reporting.user_excel import build_review_rows, build_user_rows


@dataclass(frozen=True)
class ProductionShadowInputs:
    jobs: tuple[dict[str, Any], ...]
    main_job_ids: tuple[str, ...]
    rescue_candidate_job_ids: tuple[str, ...]


def _job_id(job: dict[str, Any]) -> str:
    return str(job.get("canonical_id") or job.get("source_record_id") or "").strip()


def _calibrated_view(record: dict[str, Any]) -> dict[str, Any]:
    clone = dict(record)
    raw_extra = dict(record.get("raw_extra") or {})
    raw_extra["evaluation"] = evaluate_calibrated(record)
    clone["raw_extra"] = raw_extra
    return clone


def _visible_to_control_plane(record: dict[str, Any]) -> bool:
    if evaluate_negative_shadow(record).get("would_skip"):
        return False
    if evaluate_tier2_shadow(record).get("would_filter"):
        return False
    return True


def select_production_shadow_inputs(
    records: Iterable[dict[str, Any]],
) -> ProductionShadowInputs:
    """Mirror the current control-plane MAIN and Rescue candidate boundaries.

    MAIN is the current calibrated JOBS set. Rescue is the current REVIEW_MORE
    candidate pool, excluding MAIN by construction. The returned job objects
    carry the calibrated Rule evaluation only for post-hoc reporting/evidence;
    the independent LLM prompt builders continue to select their own fields and
    never receive Rule output.
    """

    jobs: list[dict[str, Any]] = []
    main_ids: list[str] = []
    rescue_ids: list[str] = []

    for record in records:
        job_id = _job_id(record)
        if not job_id or not _visible_to_control_plane(record):
            continue

        calibrated = _calibrated_view(record)
        jobs.append(calibrated)

        if build_user_rows([calibrated]):
            main_ids.append(job_id)
            continue

        if build_review_rows([calibrated]):
            rescue_ids.append(job_id)

    return ProductionShadowInputs(
        jobs=tuple(jobs),
        main_job_ids=tuple(main_ids),
        rescue_candidate_job_ids=tuple(rescue_ids),
    )
