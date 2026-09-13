from __future__ import annotations

import re
import unicodedata
from typing import Any

SHADOW_VERSION = "NEGATIVE_SHADOW_TIER2_V2_SPLIT"

# Tier 2 has two tracks:
# 1) ACTIVATED_SAFE rules are audited occupational identities that can be filtered
#    from the user-facing report.
# 2) SHADOW_ONLY rules remain visible for one to two weeks of observation because
#    they can overlap with legitimate research, digital-health, neurotechnology,
#    imaging, or scientific-computing roles.
_PROTECTED_RESEARCH_IDENTITY = re.compile(
    r"\b(?:post\s*-?\s*doc(?:toral)?|postdoctoral|post-doctoral|research\s+fellow|"
    r"research\s+associate|assistant\s+professor|research\s+assistant\s+professor|"
    r"lecturer|tenure\s*-?\s*track|junior\s+profess(?:or|orship)|juniorprofessor|"
    r"research\s+scientist|scientific\s+researcher|researcher|"
    r"(?:principal\s+|senior\s+)?research(?:\s+[a-z][a-z0-9-]*){0,3}\s+(?:engineer|data\s+scientist|data\s+engineer)|"
    r"scientific(?:\s+software|\s+data)?\s+engineer|"
    r"chercheur|chercheuse|enseignant-chercheur|enseignante-chercheuse|"
    r"investigador|investigadora|ricercatore|ricercatrice|onderzoeker|"
    r"wissenschaftlich(?:er|e)\s+mitarbeiter(?:in)?|forschungsingenieur(?:in)?|"
    r"ingenieur\s+de\s+recherche|ingegnere\s+di\s+ricerca|ingenier[oa]\s+de\s+investigacion|"
    r"doctoral\s+researcher|phd\s+(?:candidate|researcher)|"
    r"universit[aä]tsassistent.{0,20}postdoc|university\s+assistant.{0,20}postdoc)\b",
    re.I,
)

_ACTIVATED_SAFE_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "BI_BUSINESS_ANALYTICS_SAFE_T2",
        re.compile(
            r"\b(?:business\s+intelligence\s+analyst|bi\s+analyst|business\s+analyst|"
            r"reporting\s+analyst|insights\s+analyst|analytics\s+consultant|"
            r"business\s+intelligence\s+developer)\b",
            re.I,
        ),
        "Audited BI/business-analytics occupational identity.",
    ),
    (
        "TRAINER_VOCATIONAL_SAFE_T2",
        re.compile(
            r"\b(?:consulting\s+trainer|corporate\s+trainer|technical\s+trainer|"
            r"vocational\s+trainer|fitness\s+trainer|personal\s+trainer|"
            r"formateur|formatrice|ausbilder|ausbilderin|berufstrainer)\b",
            re.I,
        ),
        "Audited training or vocational-instruction occupational identity.",
    ),
    (
        "ENGINEERING_DISCIPLINE_SAFE_T2",
        re.compile(
            r"\b(?:mechanical\s+engineer|electrical\s+engineer|electronics?\s+engineer|"
            r"civil\s+engineer|structural\s+engineer|process\s+engineer|quality\s+engineer|"
            r"manufacturing\s+engineer|project\s+engineer|design\s+engineer)\b",
            re.I,
        ),
        "Audited conventional engineering occupational identity.",
    ),
)

_SHADOW_ONLY_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "DATA_SCIENCE_ENGINEERING_SHADOW_T2",
        re.compile(
            r"\b(?:data\s+analyst|data\s+scientist|analytics\s+engineer|data\s+engineer)\b",
            re.I,
        ),
        "Data/science engineering identity retained for observation because research overlap is plausible.",
    ),
    (
        "SOFTWARE_SYSTEMS_SIMULATION_SHADOW_T2",
        re.compile(
            r"\b(?:simulation\s+engineer|systems?\s+engineer|software\s+engineer)\b",
            re.I,
        ),
        "Software/systems/simulation engineering retained for observation because scientific overlap is plausible.",
    ),
    (
        "GENERIC_MULTILINGUAL_ENGINEERING_SHADOW_T2",
        re.compile(
            r"\b(?:ingenieur|ingenieure|ingenieurin|ingenieurinnen|ingegnere|ingeniera|ingeniero)\b",
            re.I,
        ),
        "Generic multilingual engineering identity retained in shadow until context-specific safety is proven.",
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
    """Evaluate activated-safe and retained-shadow Tier-2 title rules."""
    title = _title(job)
    protected = bool(_PROTECTED_RESEARCH_IDENTITY.search(title))
    active_matches: list[dict[str, str]] = []
    shadow_matches: list[dict[str, str]] = []

    for rule_id, pattern, rationale in _ACTIVATED_SAFE_RULES:
        if pattern.search(title):
            active_matches.append({"rule_id": rule_id, "rationale": rationale, "mode": "ACTIVATED_SAFE"})

    for rule_id, pattern, rationale in _SHADOW_ONLY_RULES:
        if pattern.search(title):
            shadow_matches.append({"rule_id": rule_id, "rationale": rationale, "mode": "SHADOW_ONLY"})

    matched = active_matches + shadow_matches
    return {
        "shadow_version": SHADOW_VERSION,
        "title": title,
        "matched": bool(matched),
        "would_skip": bool(matched) and not protected,
        "would_filter": bool(active_matches) and not protected,
        "shadow_only_candidate": bool(shadow_matches) and not protected,
        "protected": protected,
        "protection_reason": "RESEARCH_OR_ACADEMIC_TITLE" if protected else None,
        "active_matches": active_matches,
        "shadow_matches": shadow_matches,
        "matched_rules": matched,
    }
