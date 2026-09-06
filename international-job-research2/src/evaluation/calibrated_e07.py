from __future__ import annotations

import copy
import re
from typing import Any

from src.evaluation.calibrated_e04 import _jd, _title
from src.evaluation.calibrated_e062 import evaluate_calibrated as evaluate_e062

EVALUATOR_VERSION = "E0.7_DETAIL_SAFE_ROUTING_CANDIDATE"
SURFACED_RECOMMENDATIONS = {"STRONG_APPLY", "APPLY", "REVIEW"}

# E0.7 does not try to force every unresolved vacancy into the scientific
# recommendation taxonomy. It adds an independent detail-review channel so a
# plausible vacancy cannot disappear merely because the fetched page delegates
# essential requirements to another document or because detail retrieval is
# genuinely incomplete.

_PLAUSIBLE_RESEARCH_TITLE = re.compile(
    r"\b(?:post\s*-?\s*doc(?:toral)?|postdoctoral|post-doctoral|research fellow|research associate|"
    r"research scientist|scientific project manager|research project manager|research programme manager|"
    r"research program manager|lecturer|assistant professor|university assistant|universit[aä]tsassistent)\b",
    re.I,
)

_EXPLICIT_STUDENT_TITLE = re.compile(
    r"\b(?:ph\.?d\.?\s+(?:student|candidate|position|positions|studentship)|doctoral\s+(?:student|candidate|position)|"
    r"fully\s+funded\s+ph\.?d|studentship|studentische\s+mitarbeit|student assistant|internship|trainee)\b",
    re.I,
)

_EXTERNAL_ESSENTIAL_DETAIL = re.compile(
    r"(?:"
    r"(?:please\s+)?review\s+(?:the\s+)?full\s+job\s+description\s+for\s+(?:further\s+)?details?\s+and\s+essential\s+requirements?"
    r"|full\s+job\s+description\s+for\s+(?:further\s+)?details?\s+and\s+essential\s+requirements?"
    r"|(?:essential|selection)\s+(?:criteria|requirements?)\s+(?:are|is)\s+(?:available|provided)\s+(?:in|within)\s+(?:the\s+)?(?:attached|linked)?\s*(?:job\s+description|role\s+profile|pdf|document)"
    r")",
    re.I | re.S,
)

_DETAIL_UNRESOLVED = {"PARTIAL", "UNAVAILABLE", "FETCH_FAILED", "BLOCKED", "NOT_ATTEMPTED"}

# These are independently decisive from information already available and may
# suppress detail-review routing. Soft scientific-fit/no-anchor codes do not.
_HARD_SKIP_CODES = {
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
    "SENIOR_OUT_OF_TARGET_STAGE_E06",
    "EXPLICIT_TITLE_DOMAIN_MISMATCH_E06",
    "CENTRAL_COMPUTATIONAL_COGNITION_MISMATCH_E06",
}
_HARD_SKIP_PREFIXES = (
    "MANDATORY_SPECIALIST_ADVANCED_AI_",
    "MANDATORY_SPECIALIST_STEM_CELL_",
    "MANDATORY_SPECIALIST_ADVANCED_NEUROMODULATION_",
    "MANDATORY_SPECIALIST_PATCH_",
    "SPECIALIST_IMMUNOLOGIST_IDENTITY_",
)


def _description_status(job: dict[str, Any]) -> str:
    description = job.get("description") if isinstance(job.get("description"), dict) else {}
    return str(description.get("detail_status") or "UNKNOWN").upper()


def _append(values: list[str], value: str) -> list[str]:
    out = list(values)
    if value not in out:
        out.append(value)
    return out


def _has_independent_hard_skip(result: dict[str, Any], title: str) -> bool:
    if _EXPLICIT_STUDENT_TITLE.search(title):
        return True
    blockers = set(result.get("blocker_codes") or [])
    if blockers & _HARD_SKIP_CODES:
        return True
    return any(any(code.startswith(prefix) for prefix in _HARD_SKIP_PREFIXES) for code in blockers)


def _detail_review_reason(job: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str | None]:
    title = _title(job)
    text = _jd(job)
    status = _description_status(job)

    # An independently decisive role/policy blocker can be acted on without
    # fetching additional detail. This keeps the detail-review queue useful.
    if _has_independent_hard_skip(result, title):
        return False, None

    plausible_title = bool(_PLAUSIBLE_RESEARCH_TITLE.search(title))
    inherited_review = str(result.get("recommendation") or "").upper() in SURFACED_RECOMMENDATIONS

    if status in _DETAIL_UNRESOLVED:
        if plausible_title or inherited_review:
            return True, f"DETAIL_STATUS_{status}"
        return False, None

    # Some ATS pages are technically fetched as FULL but explicitly defer the
    # essential/selection criteria to a linked PDF or role profile. Treat that
    # as unresolved essential detail rather than a complete JD.
    if status == "FULL" and _EXTERNAL_ESSENTIAL_DETAIL.search(text):
        if plausible_title or inherited_review:
            return True, "ESSENTIAL_REQUIREMENTS_EXTERNAL_DOCUMENT"

    return False, None


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluate_e062(job))
    result["evaluator_version"] = EVALUATOR_VERSION
    result["base_calibrated_evaluator_version"] = "E0.6.2_CONTEXT_LOCALIZATION_CANDIDATE"

    needs_detail, detail_code = _detail_review_reason(job, result)
    result["needs_detail_review"] = needs_detail
    result["detail_review_codes"] = []
    if detail_code:
        result["detail_review_codes"] = _append(result["detail_review_codes"], detail_code)

    recommendation = str(result.get("recommendation") or "UNKNOWN").upper()
    result["operational_surface"] = recommendation in SURFACED_RECOMMENDATIONS or needs_detail
    # Detail completeness outranks recommendation presentation. A vacancy with
    # unresolved essential criteria belongs in the dedicated detail-review lane
    # even if the lower scientific layer happened to return REVIEW/APPLY.
    result["operational_route"] = (
        "NEEDS_DETAIL_REVIEW"
        if needs_detail
        else "JOBS"
        if recommendation in SURFACED_RECOMMENDATIONS
        else "HIDDEN"
    )

    evidence = copy.deepcopy(result.get("evidence") or {})
    evidence["e07"] = {
        "detail_status": _description_status(job),
        "needs_detail_review": needs_detail,
        "detail_review_codes": list(result["detail_review_codes"]),
        "operational_route": result["operational_route"],
    }
    result["evidence"] = evidence
    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
