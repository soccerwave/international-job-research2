from __future__ import annotations

import re
import unicodedata
from typing import Any

SHADOW_VERSION = "NEGATIVE_SHADOW_TIER2_V1"

# Tier 2 is intentionally more conservative than Tier 1. Generic occupational
# identities are observed only; explicit academic/research identities protect
# the title from a would-skip outcome.
_PROTECTED_RESEARCH_IDENTITY = re.compile(
    r"\b(?:post\s*-?\s*doc(?:toral)?|postdoctoral|post-doctoral|research\s+fellow|"
    r"research\s+associate|assistant\s+professor|research\s+assistant\s+professor|"
    r"lecturer|tenure\s*-?\s*track|junior\s+profess(?:or|orship)|juniorprofessor|"
    r"research\s+scientist|scientific\s+researcher|researcher|"
    r"(?:principal\s+|senior\s+)?research(?:\s+[a-z][a-z0-9-]*){0,3}\s+(?:engineer|data\s+scientist|data\s+engineer)|"
    r"scientific(?:\s+software|\s+data)?\s+engineer|ingenieur\s+de\s+recherche|"
    r"ingegnere\s+di\s+ricerca|ingenier[oa]\s+de\s+investigacion|forschungsingenieur(?:in)?|"
    r"research\s+data\s+scientist|doctoral\s+researcher|phd\s+(?:candidate|researcher)|"
    r"universit[aä]tsassistent.{0,20}postdoc|university\s+assistant.{0,20}postdoc)\b",
    re.I,
)

_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "DATA_ANALYTICS_T2",
        re.compile(
            r"\b(?:data\s+analyst|business\s+intelligence\s+analyst|bi\s+analyst|"
            r"business\s+analyst|data\s+scientist|analytics\s+engineer|data\s+engineer|"
            r"reporting\s+analyst|insights\s+analyst|analytics\s+consultant|"
            r"business\s+intelligence\s+developer)\b",
            re.I,
        ),
        "Generic data, BI or analytics occupational identity.",
    ),
    (
        "TRAINER_VOCATIONAL_T2",
        re.compile(
            r"\b(?:consulting\s+trainer|corporate\s+trainer|technical\s+trainer|"
            r"vocational\s+trainer|fitness\s+trainer|personal\s+trainer|"
            r"formateur|formatrice|ausbilder|ausbilderin|berufstrainer)\b",
            re.I,
        ),
        "Generic training or vocational-instruction occupational identity.",
    ),
    (
        "GENERIC_ENGINEERING_T2",
        re.compile(
            r"\b(?:simulation\s+engineer|systems?\s+engineer|software\s+engineer|"
            r"mechanical\s+engineer|electrical\s+engineer|electronics?\s+engineer|"
            r"civil\s+engineer|structural\s+engineer|process\s+engineer|quality\s+engineer|"
            r"manufacturing\s+engineer|project\s+engineer|design\s+engineer|"
            r"ingenieur|ingenieure|ingenieurin|ingenieurinnen|ingenieur\s+[a-z]|"
            r"ingenieurin\s+[a-z]|ingegnere|ingeniera|ingeniero|"
            r"ingenieur\s+systemes|ingenieur\s+systeme)\b",
            re.I,
        ),
        "Generic engineering occupational identity without an explicit research title.",
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


def evaluate_tier2_shadow(job: dict[str, Any]) -> dict[str, Any]:
    """Observe Tier-2 candidates without changing production routing or reporting."""
    title = _title(job)
    protected = bool(_PROTECTED_RESEARCH_IDENTITY.search(title))
    matched: list[dict[str, str]] = []

    for rule_id, pattern, rationale in _RULES:
        if pattern.search(title):
            matched.append({"rule_id": rule_id, "rationale": rationale})

    return {
        "shadow_version": SHADOW_VERSION,
        "title": title,
        "matched": bool(matched),
        "would_skip": bool(matched) and not protected,
        "protected": protected,
        "protection_reason": "RESEARCH_OR_ACADEMIC_TITLE" if protected else None,
        "matched_rules": matched,
    }
