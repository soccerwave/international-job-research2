from __future__ import annotations

import copy
import re
from typing import Any

from src.evaluation.calibrated_e04 import _jd, _title
from src.evaluation.calibrated_e06 import evaluate_calibrated as evaluate_e06

EVALUATOR_VERSION = "E0.6.1_BALANCED_RELEVANCE_CANDIDATE"

# E0.6.1 is a narrow generalization repair over E0.6. It addresses two
# error classes exposed by the burned E0.5 fresh-blind set without using
# canonical IDs: (1) specialist immunologist posts must not be rescued by
# microbiome/brain-body adjacency, and (2) epidemiology/health-data posts
# must not be hard-skipped when genomics is only an advantageous preference.

_IMMUNOLOGIST_TITLE = re.compile(r"\bimmunologist\b", re.I)
_IMMUNOLOGY_SPECIALIST_EVIDENCE = re.compile(
    r"\b(?:deep|strong|extensive|proven)\s+(?:experimental\s+)?(?:expertise|experience)\s+in\s+immunology\b|"
    r"\b(?:immune cell phenotyping|myeloid populations?|cytokine|microglial activation|neuroimmune)\b",
    re.I,
)
_EPIDEMIOLOGY_HEALTH_DATA_TITLE = re.compile(
    r"\b(?:epidemiolog(?:y|ical)|health data science|population health)\b",
    re.I,
)
_OPTIONAL_OMICS_REQUIREMENT = re.compile(
    r"\bexperience\s+of\b.{0,320}\b(?:genomic(?:s| data)?|polygenic risk scores?|multi[- ]omics?|omics)\b"
    r".{0,180}\b(?:would be advantageous|would be desirable|is desirable|is preferred|preferred|advantageous|desirable)\b",
    re.I | re.S,
)
_NON_OMICS_HARD_BLOCKERS = {
    "ROLE_STUDENT",
    "FR_FACULTY_OUT_OF_SCOPE",
    "MANDATORY_MEDICAL_OR_NURSING_DEGREE",
    "MANDATORY_PROFESSIONAL_REGISTRATION",
    "MANDATORY_GERMAN_C1_C2_TEACHING",
    "MANDATORY_GERMAN_E06",
    "MANDATORY_PATCH_CLAMP",
    "MANDATORY_OPTOGENETICS",
    "MANDATORY_SPECIALIST_WET_LAB",
    "MANDATORY_ADVANCED_AI_ML",
    "AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED",
    "AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED_E06",
    "HIGH_CONFIDENCE_UNRELATED_DOMAIN",
    "SENIOR_OUT_OF_TARGET_STAGE_E06",
    "EXPLICIT_TITLE_DOMAIN_MISMATCH_E06",
    "MANDATORY_PHD_DISCIPLINE_MISMATCH_E06",
    "CENTRAL_COMPUTATIONAL_COGNITION_MISMATCH_E06",
}
_NON_OMICS_HARD_PREFIXES = (
    "MANDATORY_SPECIALIST_ADVANCED_AI",
    "MANDATORY_SPECIALIST_STEM_CELL",
    "MANDATORY_SPECIALIST_ADVANCED_NEUROMODULATION",
    "PRESERVE_EXPLICIT_HARD_BLOCKER",
)


def _append(values: list[str], value: str) -> list[str]:
    out = list(values)
    if value not in out:
        out.append(value)
    return out


def _skip(result: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["recommendation"] = "SKIP"
    out["pre_evaluation_disposition"] = "POLICY_SKIP"
    out["blocker_codes"] = _append(list(out.get("blocker_codes") or []), code)
    out["reason"] = reason + " " + str(out.get("reason") or "")
    evidence = copy.deepcopy(out.get("evidence") or {})
    evidence["e061"] = _append(list(evidence.get("e061") or []), reason)
    out["evidence"] = evidence
    return out


def _review(result: dict[str, Any], code: str, reason: str, *, remove_blockers: set[str]) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["recommendation"] = "REVIEW"
    out["pre_evaluation_disposition"] = "POLICY_REVIEW"
    out["blocker_codes"] = [b for b in list(out.get("blocker_codes") or []) if b not in remove_blockers]
    out["review_codes"] = _append(list(out.get("review_codes") or []), code)
    out["reason"] = reason + " " + str(out.get("reason") or "")
    evidence = copy.deepcopy(out.get("evidence") or {})
    evidence["e061"] = _append(list(evidence.get("e061") or []), reason)
    out["evidence"] = evidence
    return out


def _has_non_omics_hard_blocker(job: dict[str, Any], result: dict[str, Any]) -> bool:
    inherited = set(result.get("blocker_codes") or [])
    raw_eval = ((job.get("raw_extra") or {}).get("evaluation") or {})
    inherited.update(raw_eval.get("blocker_codes") or [])
    if inherited & _NON_OMICS_HARD_BLOCKERS:
        return True
    return any(code.startswith(prefix) for code in inherited for prefix in _NON_OMICS_HARD_PREFIXES)


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluate_e06(job))
    result["evaluator_version"] = EVALUATOR_VERSION
    result["base_calibrated_evaluator_version"] = "E0.6_BALANCED_RELEVANCE_CANDIDATE"

    title = _title(job)
    text = _jd(job)
    blockers = set(result.get("blocker_codes") or [])

    # A role explicitly titled Immunologist and asking for specialist experimental
    # immunology remains outside the declared profile even if the project itself
    # concerns microbiome, brain or behaviour.
    if _IMMUNOLOGIST_TITLE.search(title) and _IMMUNOLOGY_SPECIALIST_EVIDENCE.search(text):
        return _skip(
            result,
            "SPECIALIST_IMMUNOLOGIST_IDENTITY_E061",
            "The vacancy is explicitly an Immunologist post and the advert asks for specialist experimental immunology expertise, which is not established in the declared profile.",
        )

    # E0.5/E0.6 can over-read project-level genomic mentions as a mandatory
    # specialist identity. When the central role is epidemiology/health-data
    # science and the advert explicitly says genomic/polygenic experience is
    # advantageous/desirable, retain it for human review instead of hard skip.
    # A separate hard blocker always remains decisive.
    if (
        result.get("recommendation") == "SKIP"
        and "MANDATORY_SPECIALIST_OMICS_GENOMICS_E05" in blockers
        and not _has_non_omics_hard_blocker(job, result)
        and _EPIDEMIOLOGY_HEALTH_DATA_TITLE.search(f"{title} {text}")
        and _OPTIONAL_OMICS_REQUIREMENT.search(text)
    ):
        return _review(
            result,
            "EPIDEMIOLOGY_OPTIONAL_OMICS_REVIEW_E061",
            "The central role is epidemiology/health-data research and the advert explicitly frames genomic/polygenic experience as advantageous or desirable rather than mandatory.",
            remove_blockers={"MANDATORY_SPECIALIST_OMICS_GENOMICS_E05"},
        )

    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
