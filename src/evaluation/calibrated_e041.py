from __future__ import annotations

import copy
import re
from typing import Any

from src.evaluation.calibrated_e04 import (
    ADJACENT_SCIENCE,
    DIRECT_CORE,
    SECONDARY_TRACK,
    _jd,
    _title,
    evaluate_calibrated as evaluate_e04,
)

EVALUATOR_VERSION = "E0.4.1_EVIDENCE_GATED_CANDIDATE"

# Legal/compliance/benefit text routinely contains health-related words that are not
# scientific vacancy evidence (for example the name of disability legislation).  A
# relevance matcher must not promote a vacancy because of terms that occur only after
# the substantive job description has ended.
_BOILERPLATE_START = re.compile(
    r"\b(?:equal opportunity employer|equal opportunity/affirmative action employer|"
    r"reasonable accommodation|if you are an individual with a disability|"
    r"employee benefits|compensation and benefits information|privacy notice|"
    r"background check|protected veteran status)\b",
    re.I,
)


def _substantive_relevance_text(job: dict[str, Any]) -> str:
    title = _title(job)
    body = _jd(job)
    starts = [m.start() for m in _BOILERPLATE_START.finditer(body) if m.start() >= 250]
    if starts:
        body = body[: min(starts)]
    return f"{title} {body}"


def _append_unique(values: list[str], value: str) -> list[str]:
    out = list(values)
    if value not in out:
        out.append(value)
    return out


def _skip(result: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["recommendation"] = "SKIP"
    out["pre_evaluation_disposition"] = "POLICY_SKIP"
    out["blocker_codes"] = _append_unique(list(out.get("blocker_codes") or []), code)
    out["reason"] = reason + " " + str(out.get("reason") or "")
    evidence = copy.deepcopy(out.get("evidence") or {})
    evidence["e041"] = _append_unique(list(evidence.get("e041") or []), reason)
    out["evidence"] = evidence
    return out


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluate_e04(job))
    result["evaluator_version"] = EVALUATOR_VERSION
    result["base_calibrated_evaluator_version"] = "E0.4_EVIDENCE_GATED_CANDIDATE"

    # Only reconsider a REVIEW that E0.4 created because of an adjacent scientific
    # signal.  Direct-fit, faculty-adjacent, eligibility and project-management reviews
    # are not touched by this guard.
    review_codes = set(result.get("review_codes") or [])
    if "ADJACENT_SCIENTIFIC_FIT_E04" not in review_codes:
        return result

    relevance_text = _substantive_relevance_text(job)
    if (
        not DIRECT_CORE.search(relevance_text)
        and not ADJACENT_SCIENCE.search(relevance_text)
        and not SECONDARY_TRACK.search(relevance_text)
    ):
        return _skip(
            result,
            "BOILERPLATE_ONLY_RELEVANCE_E041",
            "The only apparent profile-relevance signal occurs in legal/compliance/benefit boilerplate rather than the substantive vacancy description.",
        )

    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
