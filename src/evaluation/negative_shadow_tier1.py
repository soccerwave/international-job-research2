from __future__ import annotations

import re
import unicodedata
from typing import Any

SHADOW_VERSION = "NEGATIVE_SHADOW_TIER1_V1"

_TARGET_ACADEMIC = re.compile(
    r"\b(?:post\s*-?\s*doc(?:toral)?|postdoctoral|post-doctoral|research\s+fellow|research\s+associate|"
    r"assistant\s+professor|research\s+assistant\s+professor|lecturer|tenure\s*-?\s*track|"
    r"junior\s+profess(?:or|orship)|juniorprofessor|universit[aä]tsassistent.{0,20}postdoc|"
    r"university\s+assistant.{0,20}postdoc)\b",
    re.I,
)

_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "SCHOOL_PRIVATE_TUTORING_T1",
        re.compile(
            r"\b(?:school teacher|primary teacher|secondary teacher|private tutor|private teacher|"
            r"professeur particulier|cours particuliers|soutien scolaire|nauczyciel(?:ka|ki|ek|em|e|a)?|"
            r"korepetytor(?:ka|zy|em)?|nachhilfe(?:lehrer|lehrerin)?|lehrer(?:in)?|"
            r"insegnante privato|insegnante privata|ripetizioni|profesor particular|profesora particular)\b",
            re.I,
        ),
        "Explicit school-teaching/private-tutoring occupational identity.",
    ),
    (
        "FINANCE_BANKING_RISK_T1",
        re.compile(
            r"\b(?:credit risk|market risk|financial risk|risk stress testing|stress testing analyst|"
            r"stress testing expert|valuation control|treasury|investment analyst|financial analyst|"
            r"banking analyst|credit analyst|model risk|counterparty risk|liquidity risk)\b",
            re.I,
        ),
        "Explicit finance/banking/risk occupational context, including financial stress testing.",
    ),
    (
        "CLINICAL_PRACTITIONER_T1",
        re.compile(
            r"\b(?:general practitioner|physician|medical doctor|resident physician|consultant physician|"
            r"registered nurse|staff nurse|clinical nurse|assistenzarzt(?:in)?|facharzt(?:in)?|"
            r"oberarzt(?:in)?|medecin|huisarts)\b",
            re.I,
        ),
        "Explicit clinical-practitioner occupational identity.",
    ),
    (
        "SALES_HR_COMMERCIAL_T1",
        re.compile(
            r"\b(?:sales manager|sales executive|account executive|account manager|business development manager|"
            r"business development executive|commercial manager|recruiter|talent acquisition|hr manager|"
            r"human resources manager|people partner|customer success manager)\b",
            re.I,
        ),
        "Explicit sales, HR, recruiting, commercial or customer-success identity.",
    ),
    (
        "ADMIN_OPERATIONS_T1",
        re.compile(
            r"\b(?:administrator|administrative officer|administration officer|operations manager|operations officer|"
            r"operations coordinator|programme coordinator|program coordinator|project coordinator|office manager|"
            r"student services officer|student services assistant|faculty administrator|school administrator)\b",
            re.I,
        ),
        "Explicit administrative or operational identity outside the configured research target.",
    ),
)


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def _title(job: dict[str, Any]) -> str:
    position = job.get("position") or {}
    return _norm(position.get("title_raw") or position.get("title_normalized") or "")


def evaluate_negative_shadow(job: dict[str, Any]) -> dict[str, Any]:
    """Observe Tier-1 negative rules without changing any production route."""
    title = _title(job)

    # Tier-1 rules describe explicit non-target occupational identities. A thematic
    # phrase such as rehabilitation, public health, or physical activity must not
    # override an explicit clinician/administrator/teacher identity. Only an actual
    # configured academic target identity in the title protects a matched vacancy.
    protected = bool(_TARGET_ACADEMIC.search(title))
    protection_reason = "TARGET_ACADEMIC_TITLE" if protected else None

    matched: list[dict[str, str]] = []
    for rule_id, pattern, rationale in _RULES:
        if pattern.search(title):
            matched.append({"rule_id": rule_id, "rationale": rationale})

    would_skip = bool(matched) and not protected
    return {
        "shadow_version": SHADOW_VERSION,
        "title": title,
        "matched": bool(matched),
        "would_skip": would_skip,
        "protected": protected,
        "protection_reason": protection_reason,
        "matched_rules": matched,
    }
