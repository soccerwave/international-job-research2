from __future__ import annotations

import copy
import re
from typing import Any

from src.evaluation.calibrated_e04 import _jd
from src.evaluation.calibrated_e05 import evaluate_calibrated as evaluate_e05
from src.evaluation.calibrated_e061 import evaluate_calibrated as evaluate_e061

EVALUATOR_VERSION = "E0.6.2_CONTEXT_LOCALIZATION_CANDIDATE"
SURFACED = {"STRONG_APPLY", "APPLY", "REVIEW"}

# E0.6.2 repairs two context-localization errors exposed by older burned evidence:
# 1) a high language level is not mandatory when the same sentence explicitly
#    marks it as desirable/preferred; and
# 2) a generic "PhD or equivalent experience" clause must not become a PhD-field
#    blocker merely because an unrelated discipline word occurs later in prose.

_GERMAN = re.compile(r"\bgerman\b|\bdeutsch(?:kenntnisse)?\b", re.I)
_GERMAN_PREFERENCE = re.compile(
    r"\b(?:w[uü]nschenswert|erw[uü]nscht|idealerweise|von\s+vorteil|preferred|preferably|desirable|advantageous)\b",
    re.I,
)
_GERMAN_MANDATORY = re.compile(
    r"\b(?:mandatory|required|essential|must|vorausgesetzt|erforderlich|zwingend|muss|m[uü]ssen)\b",
    re.I,
)

_MISMATCH_FIELDS = (
    r"organizational psychology|organisational psychology|work and organizational psychology|"
    r"work & organizational psychology|social psychology|management|marketing|business|law|"
    r"engineering|chemistry|physics"
)
_EXPLICIT_MISMATCH_PHD = re.compile(
    rf"\b(?:ph\.?d\.?|doctorate|doctoral degree)\b.{{0,70}}\b(?:in|within|in the field of)\b.{{0,100}}"
    rf"\b(?:{_MISMATCH_FIELDS})\b",
    re.I | re.S,
)
_OTHER_HARD_CODES = {
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
    "MANDATORY_ADVANCED_FMRI_ANALYSIS_E042",
    "AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED",
    "AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED_E06",
    "HIGH_CONFIDENCE_UNRELATED_DOMAIN",
    "SENIOR_OUT_OF_TARGET_STAGE_E06",
    "EXPLICIT_TITLE_DOMAIN_MISMATCH_E06",
    "CENTRAL_COMPUTATIONAL_COGNITION_MISMATCH_E06",
    "CENTRAL_MOLECULAR_WETLAB_E04",
    "NON_TARGET_ROLE_IDENTITY_E05",
    "SPECIALIST_IMMUNOLOGIST_IDENTITY_E061",
}
_OTHER_HARD_PREFIXES = (
    "MANDATORY_SPECIALIST_",
    "MANDATORY_ADVANCED_",
    "PRESERVE_EXPLICIT_HARD_BLOCKER",
    "INHERITED_EXPLICIT_HARD",
    "SPECIALIST_",
)
_PHD_CONTEXT_REMOVABLE = {
    "MANDATORY_PHD_DISCIPLINE_MISMATCH_E06",
    "NO_PROFILE_ANCHOR_IN_FULL_JD_E021",
    "NO_PROFILE_RELEVANCE_EVIDENCE_E04",
    "INSUFFICIENT_RELEVANCE_EVIDENCE_E04",
}


def _append(values: list[str], value: str) -> list[str]:
    out = list(values)
    if value not in out:
        out.append(value)
    return out


def _german_is_explicitly_preferred(text: str) -> bool:
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
        if not _GERMAN.search(sentence):
            continue
        if _GERMAN_PREFERENCE.search(sentence) and not _GERMAN_MANDATORY.search(sentence):
            return True
    return False


def _has_other_hard_blocker(blockers: set[str], *, ignore: set[str]) -> bool:
    for code in blockers - ignore:
        if code in _OTHER_HARD_CODES:
            return True
        if any(code.startswith(prefix) for prefix in _OTHER_HARD_PREFIXES):
            return True
    return False


def _restore_surfaced_from_e05(job: dict[str, Any], result: dict[str, Any], *, code: str, reason: str) -> dict[str, Any]:
    base = copy.deepcopy(evaluate_e05(job))
    base_rec = str(base.get("recommendation") or "").upper()
    if base_rec not in SURFACED:
        return result
    out = base
    out["evaluator_version"] = EVALUATOR_VERSION
    out["base_calibrated_evaluator_version"] = "E0.6.1_BALANCED_RELEVANCE_CANDIDATE"
    out["review_codes"] = _append(list(out.get("review_codes") or []), code)
    out["reason"] = reason + " " + str(out.get("reason") or "")
    evidence = copy.deepcopy(out.get("evidence") or {})
    evidence["e062"] = _append(list(evidence.get("e062") or []), reason)
    out["evidence"] = evidence
    return out


def _force_review(result: dict[str, Any], *, code: str, reason: str, remove_blockers: set[str]) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["recommendation"] = "REVIEW"
    out["pre_evaluation_disposition"] = "POLICY_REVIEW"
    out["blocker_codes"] = [b for b in list(out.get("blocker_codes") or []) if b not in remove_blockers]
    out["review_codes"] = _append(list(out.get("review_codes") or []), code)
    out["evaluator_version"] = EVALUATOR_VERSION
    out["base_calibrated_evaluator_version"] = "E0.6.1_BALANCED_RELEVANCE_CANDIDATE"
    out["reason"] = reason + " " + str(out.get("reason") or "")
    evidence = copy.deepcopy(out.get("evidence") or {})
    evidence["e062"] = _append(list(evidence.get("e062") or []), reason)
    out["evidence"] = evidence
    return out


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluate_e061(job))
    result["evaluator_version"] = EVALUATOR_VERSION
    result["base_calibrated_evaluator_version"] = "E0.6.1_BALANCED_RELEVANCE_CANDIDATE"

    text = _jd(job)
    blockers = set(result.get("blocker_codes") or [])

    # If E0.6 introduced only a German blocker, but the same language sentence
    # explicitly says the C-level German is desirable/preferred, that blocker is
    # unsupported. Restore the pre-E0.6 surfaced recommendation.
    if blockers == {"MANDATORY_GERMAN_E06"} and _german_is_explicitly_preferred(text):
        return _restore_surfaced_from_e05(
            job,
            result,
            code="GERMAN_PREFERRED_NOT_MANDATORY_E062",
            reason="The advert explicitly frames German proficiency as desirable/preferred rather than mandatory; a stated C-level alone is not blocker evidence.",
        )

    # A PhD-field blocker needs an explicit syntactic relation between the PhD
    # and the mismatching discipline. If that relation is absent and there is no
    # separate hard blocker, fail open to REVIEW. Soft relevance codes do not
    # justify hard-skipping the vacancy.
    if (
        "MANDATORY_PHD_DISCIPLINE_MISMATCH_E06" in blockers
        and not _EXPLICIT_MISMATCH_PHD.search(text)
        and not _has_other_hard_blocker(blockers, ignore={"MANDATORY_PHD_DISCIPLINE_MISMATCH_E06"})
    ):
        return _force_review(
            result,
            code="PHD_DISCIPLINE_CONTEXT_NOT_EXPLICIT_E062",
            reason="The advert does not explicitly require a PhD in the mismatching discipline; nearby management/domain wording is insufficient to establish a doctoral-field blocker.",
            remove_blockers=_PHD_CONTEXT_REMOVABLE,
        )

    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
