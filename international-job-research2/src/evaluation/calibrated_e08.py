from __future__ import annotations

import copy
import re
from typing import Any

from src.evaluation.calibrated_e04 import _jd, _title
from src.evaluation.calibrated_e07 import evaluate_calibrated as evaluate_e07

EVALUATOR_VERSION = "E0.8_ROUTING_GENERALIZATION_CANDIDATE"
SURFACED_RECOMMENDATIONS = {"STRONG_APPLY", "APPLY", "REVIEW"}

# E0.8 is a new development candidate. E0.7 remains immutable and rejected.
# The rules below address general routing classes exposed by E0.7's burned
# fresh-blind set: target-stage open-topic recovery, independently clear
# unrelated-domain precedence, and broader external-detail delegation.

_SOFT_NO_FIT_CODES = {
    "NO_PROFILE_ANCHOR_IN_FULL_JD_E021",
    "NO_PROFILE_RELEVANCE_EVIDENCE_E04",
    "INSUFFICIENT_RELEVANCE_EVIDENCE_E04",
}

_TARGET_JUNIOR_OPEN_TOPIC = re.compile(
    r"\b(?:w\s*1|junior\s+profess(?:or|orship)|tenure\s*-?\s*track)\b",
    re.I,
)
_OPEN_TOPIC = re.compile(r"\b(?:open\s+topic|open\s+field|open\s+discipline|topic\s+open)\b", re.I)
_RELEVANT_FACULTY_AREA = re.compile(
    r"\b(?:neuroscien(?:ce|ces)|brain(?:\s+health)?|ageing|aging|stress(?:\s+biology)?|"
    r"exercise(?:\s+science|\s+physiology)?|physical\s+activity|physiology|behavio[u]?ral\s+medicine|"
    r"rehabilitation|digital\s+health|healthy\s+ageing|healthy\s+aging)\b",
    re.I,
)
_AREA_CONTEXT = re.compile(
    r"\b(?:key|core|main|strategic|priority|focus)\s+(?:research\s+)?areas?\b|"
    r"\bresearch\s+(?:areas?|priorities|themes|fields)\b",
    re.I,
)

# External-detail delegation can appear in multiple ATS phrasings. These
# patterns are deliberately semantic classes rather than institution strings.
_EXTERNAL_DETAIL_DELEGATION = re.compile(
    r"(?:"
    r"(?:please\s+)?review\s+(?:the\s+)?full\s+job\s+description\s+for\s+(?:further\s+)?details?\s+and\s+essential\s+requirements?"
    r"|full\s+job\s+description\s+for\s+(?:further\s+)?details?\s+and\s+essential\s+requirements?"
    r"|(?:essential|selection)\s+(?:criteria|requirements?)\s+(?:are|is)\s+(?:available|provided)\s+(?:in|within)\s+(?:the\s+)?(?:attached|linked)?\s*(?:job\s+description|role\s+profile|pdf|document)"
    r"|(?:information|candidate|recruitment|application)\s+(?:pack|package|brief)\b.{0,180}\b(?:full\s+details?|selection\s+criteria|essential\s+requirements?|application\s+process)\b"
    r"|\bfull\s+details?\s+of\s+the\s+(?:post|role|position)\b.{0,180}\b(?:selection\s+criteria|essential\s+requirements?|application\s+process)\b"
    r"|\b(?:full|complete)\s+(?:selection\s+criteria|essential\s+criteria|person\s+specification)\b.{0,120}\b(?:see|available|download|attached|link|package|pack|document|pdf)\b"
    r")",
    re.I | re.S,
)

# High-confidence specialist identities that are independently outside this
# project's declared scientific tracks. The gate requires title/JD identity,
# not incidental mentions of engineering or technology.
_UNRELATED_TITLE_OR_PROJECT = re.compile(
    r"\b(?:timber\s+engineering|structural\s+engineering|civil\s+engineering|"
    r"construction\s+engineering|wood\s+engineering|hydrogeology|hydrology|"
    r"robotics|control\s+systems?\s+technology|electrical\s+engineering|"
    r"electronic\s+engineering|quantum\s+(?:physics|optics)|laser\s+physics|"
    r"video\s+(?:compression|processing)|energy[- ]efficient\s+ai|"
    r"medicinal\s+chemistry|oral\s+lipid\s+based\s+formulations?|plant\s+immunity)\b",
    re.I,
)
_MEDICAL_DEVICE_ENGINEERING = re.compile(
    r"\b(?:medical\s+device|medtech|stent|device\s+development|device\s+engineering|"
    r"diagnostic\s+and\s+therapeutic\s+medical\s+devices?)\b",
    re.I,
)
_ENGINEERING_IDENTITY = re.compile(
    r"\b(?:school|department|faculty)\s+of\s+engineering\b|\bengineering\s+research\s+(?:group|lab|laboratory)\b",
    re.I,
)
_DIRECT_PROFILE_SCIENCE = re.compile(
    r"\b(?:exercise|physical\s+activity|sport\s+science|exercise\s+physiology|neuroscien(?:ce|ces)|"
    r"psychosocial\s+stress|stress\s+biology|cortisol|hpa\s+axis|brain\s+health|"
    r"healthy\s+ageing|healthy\s+aging|rehabilitation|behavio[u]?ral\s+medicine|digital\s+health)\b",
    re.I,
)

_INDEPENDENT_HARD_CODES = {
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
    "MANDATORY_PHD_DISCIPLINE_MISMATCH_E06",
}
_INDEPENDENT_HARD_PREFIXES = (
    "MANDATORY_SPECIALIST_ADVANCED_AI_",
    "MANDATORY_SPECIALIST_STEM_CELL_",
    "MANDATORY_SPECIALIST_ADVANCED_NEUROMODULATION_",
    "MANDATORY_SPECIALIST_PATCH_",
    "SPECIALIST_IMMUNOLOGIST_IDENTITY_",
    "MANDATORY_CORU_REGISTRATION_",
    "HIGH_CONFIDENCE_UNRELATED_TITLE_",
    "FACULTY_DISCIPLINE_MISMATCH_",
    "INHERITED_EXPLICIT_HARD_",
)


def _append(values: list[str], value: str) -> list[str]:
    out = list(values)
    if value not in out:
        out.append(value)
    return out


def _has_independent_hard_blocker(result: dict[str, Any]) -> bool:
    blockers = set(result.get("blocker_codes") or [])
    if blockers & _INDEPENDENT_HARD_CODES:
        return True
    return any(any(code.startswith(prefix) for prefix in _INDEPENDENT_HARD_PREFIXES) for code in blockers)


def _only_soft_no_fit_blockers(result: dict[str, Any]) -> bool:
    blockers = set(result.get("blocker_codes") or [])
    return bool(blockers) and blockers.issubset(_SOFT_NO_FIT_CODES)


def _relevant_open_topic_context(text: str) -> bool:
    # Require a research-area phrase and a declared-profile field reasonably
    # nearby. This prevents a generic institution-wide neuroscience mention
    # from rescuing an open-topic role in an unrelated faculty.
    for area in _AREA_CONTEXT.finditer(text):
        start = max(0, area.start() - 100)
        end = min(len(text), area.end() + 320)
        if _RELEVANT_FACULTY_AREA.search(text[start:end]):
            return True
    return False


def _independently_unrelated_domain(title: str, text: str, result: dict[str, Any]) -> bool:
    # Never let this helper override a lower-layer positive scientific judgment;
    # it is only a precision guard for SKIP cases being rescued by detail fallback.
    if str(result.get("recommendation") or "").upper() != "SKIP":
        return False

    title_and_front = f"{title} {text[:2600]}"
    if _UNRELATED_TITLE_OR_PROJECT.search(title_and_front):
        return True

    # Medical-device engineering can contain generic patient/clinical language.
    # Require both an engineering organizational identity and central device
    # terminology, and do not suppress if direct declared-profile science is present.
    if _ENGINEERING_IDENTITY.search(title_and_front) and _MEDICAL_DEVICE_ENGINEERING.search(title_and_front):
        if not _DIRECT_PROFILE_SCIENCE.search(title_and_front):
            return True
    return False


def _set_review(result: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["recommendation"] = "REVIEW"
    out["pre_evaluation_disposition"] = "POLICY_REVIEW"
    out["blocker_codes"] = [b for b in list(out.get("blocker_codes") or []) if b not in _SOFT_NO_FIT_CODES]
    out["review_codes"] = _append(list(out.get("review_codes") or []), code)
    out["reason"] = reason + " " + str(out.get("reason") or "")
    return out


def _set_detail(result: dict[str, Any], code: str) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["needs_detail_review"] = True
    out["detail_review_codes"] = _append(list(out.get("detail_review_codes") or []), code)
    out["operational_surface"] = True
    out["operational_route"] = "NEEDS_DETAIL_REVIEW"
    return out


def _clear_detail_hidden(result: dict[str, Any], code: str) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["needs_detail_review"] = False
    out["detail_review_codes"] = []
    out["operational_surface"] = False
    out["operational_route"] = "HIDDEN"
    evidence = copy.deepcopy(out.get("evidence") or {})
    evidence.setdefault("e08", {})["detail_suppression_code"] = code
    out["evidence"] = evidence
    return out


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluate_e07(job))
    result["evaluator_version"] = EVALUATOR_VERSION
    result["base_calibrated_evaluator_version"] = "E0.7_DETAIL_SAFE_ROUTING_CANDIDATE"

    title = _title(job)
    text = _jd(job)
    combined = f"{title} {text}"

    # 1) Recover target-stage open-topic junior/tenure-track appointments only
    # when the posting itself places the role in a clearly relevant research
    # area and lower-layer blockers are merely lack-of-anchor signals.
    if (
        str(result.get("recommendation") or "").upper() == "SKIP"
        and _TARGET_JUNIOR_OPEN_TOPIC.search(title)
        and _OPEN_TOPIC.search(combined)
        and _relevant_open_topic_context(text)
        and _only_soft_no_fit_blockers(result)
        and not _has_independent_hard_blocker(result)
    ):
        result = _set_review(
            result,
            "TARGET_STAGE_RELEVANT_OPEN_TOPIC_REVIEW_E08",
            "The role is a target-stage junior/tenure-track open-topic appointment explicitly situated in relevant faculty research areas; human fit review is warranted rather than automatic exclusion.",
        )

    # 2) Broaden external-detail delegation. Explicit independent blockers from
    # the available page outrank missing external criteria, so the detail lane
    # does not become a catch-all for clearly unrelated or ineligible roles.
    if _EXTERNAL_DETAIL_DELEGATION.search(text) and not _has_independent_hard_blocker(result):
        if str(result.get("recommendation") or "").upper() in SURFACED_RECOMMENDATIONS or re.search(
            r"\b(?:post\s*-?\s*doc(?:toral)?|research\s+(?:fellow|associate|scientist)|assistant\s+professor|lecturer|junior\s+profess)\b",
            title,
            re.I,
        ):
            result = _set_detail(result, "ESSENTIAL_REQUIREMENTS_EXTERNAL_DOCUMENT_E08")

    # 3) An external PDF must not rescue a role whose available information
    # already establishes an unrelated specialist domain with high confidence.
    if result.get("needs_detail_review") and _independently_unrelated_domain(title, text, result):
        result = _clear_detail_hidden(result, "INDEPENDENT_UNRELATED_DOMAIN_BEFORE_DETAIL_FALLBACK_E08")

    # Recompute route in case scientific recovery occurred without detail need.
    recommendation = str(result.get("recommendation") or "UNKNOWN").upper()
    if not result.get("needs_detail_review"):
        result["operational_surface"] = recommendation in SURFACED_RECOMMENDATIONS
        result["operational_route"] = "JOBS" if recommendation in SURFACED_RECOMMENDATIONS else "HIDDEN"

    evidence = copy.deepcopy(result.get("evidence") or {})
    evidence["e08"] = {
        **(evidence.get("e08") if isinstance(evidence.get("e08"), dict) else {}),
        "needs_detail_review": bool(result.get("needs_detail_review")),
        "detail_review_codes": list(result.get("detail_review_codes") or []),
        "operational_route": result.get("operational_route"),
    }
    result["evidence"] = evidence
    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
