from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any

EVALUATOR_VERSION = "E0.2_CALIBRATED_SHADOW"
GOOD_DETAIL = {"FULL", "PARTIAL"}
PRIMARY_FAMILIES = {
    "POSTDOC",
    "RESEARCH_FELLOW_POSTDOC",
    "ASSISTANT_PROFESSOR",
    "LECTURER",
    "RESEARCH_ASSISTANT_PROFESSOR",
    "TENURE_TRACK",
    "JUNIOR_PROFESSOR",
}
SECONDARY_FAMILIES = {
    "RESEARCH_SCIENTIST",
    "SCIENTIFIC_PROJECT_MANAGER",
    "RESEARCH_PROJECT_MANAGER",
    "RESEARCH_PROGRAMME_MANAGER",
}

EXERCISE_CORE = {
    "exercise physiology": r"\bexercise physiology\b",
    "exercise science": r"\bexercise science\b",
    "sport science": r"\bsport(?:s)? science\b",
    "sport and exercise": r"\bsport and exercise\b",
    "physical activity": r"\bphysical activity\b",
    "human movement": r"\bhuman movement\b",
    "kinesiology": r"\bkinesiology\b",
    "clinical exercise": r"\bclinical exercise\b",
    "fitness": r"\bfitness\b",
    "exercise intervention": r"\bexercise intervention(?:s)?\b",
    "exercise training": r"\bexercise training\b",
    "aerobic exercise": r"\baerobic exercise\b",
    "resistance training": r"\bresistance training\b",
    "physical training": r"\bphysical training\b",
    "sports medicine": r"\bsports medicine\b",
}

STRESS_NEURO_CORE = {
    "exercise neuroscience": r"\bexercise neuroscience\b",
    "stress biology": r"\bstress biology\b",
    "psychophysiology": r"\bpsychophysiolog(?:y|ical)\b",
    "psychosocial stress": r"\bpsychosocial stress\b",
    "psychological stress": r"\bpsychological stress\b",
    "stress recovery": r"\bstress recovery\b",
    "stress response": r"\bstress response\b",
    "cortisol": r"\bcortisol\b",
    "HPA axis": r"\bhpa(?:-| )axis\b",
    "brain health": r"\bbrain health\b",
    "neurocognitive health": r"\bneurocognitive health\b",
}

# Generic full-JD phrases such as employee "fitness" benefits and campus "sport and
# exercise" facilities caused major false positives in E0.1. They are only accepted
# when they occur in the vacancy title/department context, not as standalone body hits.
TEXT_CORE = {
    **{key: value for key, value in EXERCISE_CORE.items() if key not in {"fitness", "sport and exercise"}},
    **STRESS_NEURO_CORE,
}
TITLE_CORE = {
    **EXERCISE_CORE,
    **STRESS_NEURO_CORE,
    "Sportwissenschaft": r"\bsportwissenschaft\w*\b",
    "Bewegungswissenschaft": r"\bbewegungswissenschaft\w*\b",
}

ADJACENT = {
    "healthy ageing": r"\bhealthy ag(?:e|ei)ing\b",
    "lifestyle intervention": r"\blifestyle intervention(?:s)?\b",
    "behavioral medicine": r"\bbehavio(?:u)?ral medicine\b",
    "behavioral health": r"\bbehavio(?:u)?ral health\b",
    "mental health intervention": r"\bmental health intervention(?:s)?\b",
    "rehabilitation": r"\brehabilitation\b",
    "health promotion": r"\bhealth promotion\b",
    "digital health": r"\bdigital health\b",
    "wearables": r"\bwearable(?:s)?\b",
    "behavior change": r"\bbehavio(?:u)?r change\b",
    "cognitive neuroscience": r"\bcognitive neuroscience\b",
    "cognition": r"\bcognition\b",
}
TITLE_ADJACENT = {
    **ADJACENT,
    "cognitive": r"\bcognitive\b",
    "neuroscience": r"\bneuroscien(?:ce|tist|tific)\b",
    "psychology": r"\bpsycholog(?:y|ical|ist)\b",
    "mental health": r"\bmental health\b",
    "public health": r"\bpublic health\b",
    "physiotherapy": r"\bphysiotherap(?:y|ist)\b",
    "wellbeing": r"\bwell-?being\b|\bwellbeing\b",
    "stress": r"\bstress\b",
    "epidemiology": r"\bepidemiolog(?:y|ical|ist)\b",
    "health data science": r"\bhealth data science\b",
    "population health": r"\bpopulation health\b",
    "brain ageing": r"\bbrain ag(?:e|ei)ing\b",
    "parkinson": r"\bparkinson(?:'s|s)?\b",
}

UNRELATED_TITLE_PATTERNS = {
    "law": r"\b(?:international law|law|legal|lawtech)\b",
    "optics_photonics": r"\b(?:meta-?optics|optical|photonics?|nanophotonic)\b",
    "computer_ai_systems": r"\b(?:computer science|networked systems|data engineering|cybersecurity|artificial intelligence|ai|machine learning|reinforcement learning)\b",
    "earth_geoscience": r"\b(?:earth sciences?|geolog(?:y|ical)|geoscience|hydrogeolog(?:y|ical)|hydrology)\b",
    "chemistry": r"\b(?:chemistry|chemical|organometallic|catalysis)\b",
    "plant_agriculture": r"\b(?:plant science|agriculture|agrifood|agronomy|crop science|plant breeding)\b",
    "business": r"\b(?:marketing|accounting|corporate finance|finance)\b",
    "social_care": r"\b(?:social care|social policy)\b",
    "regulated_health_profession": r"\b(?:nursing|midwifery|optometry|speech and language therapy|veterinary|small animal)\b",
    "physics_quantum": r"\b(?:astronomy|astrophysics|quantum|laser physics|condensed matter)\b",
    "engineering": r"\b(?:power systems?|civil engineering|electrical and electronic engineering|engineering materials|structural engineering)\b",
    "economics": r"\b(?:economics?|econometrics)\b",
    "archaeology": r"\barchaeolog(?:y|ical)\b",
}

SPECIALIST_REVIEW_TITLE = {
    "immunology": r"\bimmunolog(?:y|ist)\b",
    "integrative biology": r"\bintegrative biolog(?:y|ist)\b",
    "systems neuroscience": r"\bsystems neuroscien(?:ce|tist)\b",
    "bioinformatics": r"\bbioinformatics?\b",
    "computational biology": r"\bcomputational biolog(?:y|ist)\b",
    "health data science": r"\bhealth data science\b",
    "epidemiology": r"\bepidemiolog(?:y|ical|ist)\b",
}

OUT_OF_SCOPE_STUDENT = re.compile(
    r"(?:^|\b)(?:phd(?:\s+position(?:s)?)?|doctoral\s+(?:position|student|candidate|researcher|fellowship|fellowships|programme|program)|doctoral\s+training)(?:\b|$)",
    re.I,
)
OUT_OF_SCOPE_SUPPORT = re.compile(
    r"\b(?:research assistant|research technician|research support officer|support officer|discipline librarian|research officer)\b",
    re.I,
)
POSTDOC_TOKEN = re.compile(r"\b(?:postdoc|post-doc|postdoctoral|post-doctoral)\b", re.I)


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def _flatten(job: dict[str, Any]) -> tuple[str, str]:
    position = job.get("position") or {}
    req = job.get("requirements") or {}
    desc = job.get("description") or {}
    title = _norm(position.get("title_raw") or position.get("title_normalized") or "")
    parts = [
        title,
        position.get("department") or "",
        position.get("institution_raw") or "",
        req.get("degree_text") or "",
        " ".join(req.get("degree_fields") or []),
        " ".join(req.get("methods_required") or []),
        " ".join(req.get("methods_preferred") or []),
        req.get("professional_registration_text") or "",
        desc.get("full_jd") or "",
    ]
    return title, _norm(" ".join(str(part) for part in parts if part))


def _hits(text: str, patterns: dict[str, str]) -> list[str]:
    return [label for label, pattern in patterns.items() if re.search(pattern, text, re.I)]


def _scientific_dimension(title: str, text: str) -> tuple[str, list[str], str | None, bool]:
    core_hits = _hits(text, TEXT_CORE)
    adjacent_hits = _hits(text, ADJACENT)
    title_core = _hits(title, TITLE_CORE)
    title_adjacent = _hits(title, TITLE_ADJACENT)
    title_unrelated = _hits(title, UNRELATED_TITLE_PATTERNS)
    specialist_review = bool(_hits(title, SPECIALIST_REVIEW_TITLE)) and not bool(title_core)
    evidence: list[str] = []

    if core_hits:
        evidence.append("Calibrated core scientific signals: " + ", ".join(core_hits[:8]))
    if title_core:
        evidence.append("Direct core title signal: " + ", ".join(title_core[:4]))
    if title_adjacent:
        evidence.append("Adjacent title signal: " + ", ".join(title_adjacent[:4]))
    if adjacent_hits:
        evidence.append("Calibrated adjacent signals: " + ", ".join(adjacent_hits[:6]))

    # A clearly unrelated title wins only when the title itself carries no relevant
    # core/adjacent signal. This prevents e.g. NeuroAI from being treated like pure AI.
    if title_unrelated and not title_core and not title_adjacent:
        evidence.append("High-confidence unrelated title domain: " + ", ".join(title_unrelated[:4]))
        return "WEAK", evidence, "HIGH_CONFIDENCE_UNRELATED_TITLE_E02", specialist_review
    if len(core_hits) >= 2 or title_core:
        return "STRONG", evidence, None, specialist_review
    if core_hits:
        return "GOOD", evidence, None, specialist_review
    # A single adjacent word in generic body text is not enough. The title must be
    # adjacent or at least two independent adjacent signals must occur in the posting.
    if title_adjacent or len(adjacent_hits) >= 2:
        return "ADJACENT", evidence, None, specialist_review
    return "UNCLEAR", evidence, None, specialist_review


def _mandatory_coru(text: str) -> bool:
    if not re.search(r"\bcoru\b", text, re.I):
        return False
    return bool(
        re.search(r"\b(?:must|required|essential|eligible|eligibility|registered|registration)\b.{0,100}\bcoru\b", text, re.I)
        or re.search(r"\bcoru\b.{0,100}\b(?:must|required|essential|eligible|eligibility|registered|registration)\b", text, re.I)
    )


def _material_review_codes(codes: list[str]) -> list[str]:
    # Scientific-domain and local-title ambiguity are recalculated here. Other Stage-7
    # review signals remain authoritative in the shadow calibration.
    ignored = {"UNCLEAR_DOMAIN", "UNCERTAIN_LOCAL_TITLE", "GENERIC_RESEARCH_FELLOW"}
    return [code for code in codes if code not in ignored]


def _role_override(title: str, role_family: str, role_status: str, level: str) -> tuple[str, str, str]:
    # E0.1 incorrectly treated titles such as "Post-Doctoral Researcher" as doctoral
    # student roles because it only exempted the literal token "postdoc". Correct that
    # in the shadow evaluator without mutating the frozen E0.1 implementation.
    if POSTDOC_TOKEN.search(title):
        return "POSTDOC", "PRIMARY", "STRONG"
    if re.search(r"\b(?:assistant professor|research assistant professor|tenure[- ]track|juniorprofessor)\b", title, re.I):
        family = "ASSISTANT_PROFESSOR" if "assistant professor" in title else role_family
        return family, "PRIMARY", "ACCEPTABLE" if level in {"UNKNOWN", "MISMATCH", "REVIEW"} else level
    if re.search(r"\blecturer\b", title, re.I) and not re.search(r"\b(?:associate|senior)\s+lecturer\b", title, re.I):
        return "LECTURER", "PRIMARY", "ACCEPTABLE" if level in {"UNKNOWN", "MISMATCH", "REVIEW"} else level
    if re.search(r"\b(?:associate professor|full professor|professor of)\b", title, re.I):
        return "OUT_OF_SCOPE", "OUT_OF_SCOPE", "MISMATCH"
    return role_family, role_status, level


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    raw_extra = job.get("raw_extra") or {}
    base = copy.deepcopy(raw_extra.get("evaluation") or job.get("evaluation") or {})
    title, text = _flatten(job)
    role_family = str(base.get("role_family") or (job.get("position") or {}).get("role_family") or "UNKNOWN").upper()
    role_status = str(base.get("role_policy_status") or "AMBIGUOUS").upper()
    dimensions = copy.deepcopy(base.get("dimensions") or {})
    level = str(dimensions.get("level") or "UNKNOWN").upper()
    role_family, role_status, level = _role_override(title, role_family, role_status, level)
    dimensions["level"] = level

    detail_status = str((job.get("description") or {}).get("detail_status") or "NOT_ATTEMPTED").upper()
    detail_missing = detail_status not in GOOD_DETAIL or not _norm((job.get("description") or {}).get("full_jd") or "")

    scientific, scientific_evidence, unrelated_code, specialist_review = _scientific_dimension(title, text)
    dimensions["scientific"] = scientific

    blocker_codes = [
        code for code in (base.get("blocker_codes") or [])
        if code != "HIGH_CONFIDENCE_UNRELATED_DOMAIN"
    ]
    if POSTDOC_TOKEN.search(title):
        blocker_codes = [code for code in blocker_codes if code != "ROLE_STUDENT"]
    review_codes = _material_review_codes(list(base.get("review_codes") or []))
    evidence = copy.deepcopy(base.get("evidence") or {})
    evidence["scientific"] = scientific_evidence
    calibration_evidence: list[str] = []

    if OUT_OF_SCOPE_STUDENT.search(title) and not POSTDOC_TOKEN.search(title):
        blocker_codes.append("ROLE_STUDENT_E02")
        calibration_evidence.append("Title explicitly identifies a PhD/doctoral training position rather than a postdoctoral role")
    if OUT_OF_SCOPE_SUPPORT.search(title) and role_family not in PRIMARY_FAMILIES:
        blocker_codes.append("ROLE_SUPPORT_OR_ASSISTANT_E02")
        calibration_evidence.append("Title explicitly identifies a non-target research support/assistant role")
    if unrelated_code:
        blocker_codes.append(unrelated_code)
    if _mandatory_coru(text):
        blocker_codes.append("MANDATORY_CORU_REGISTRATION_E02")
        dimensions["registration"] = "BLOCKED"
        calibration_evidence.append("CORU registration/eligibility is explicitly required and is not established in the profile")
    if specialist_review:
        calibration_evidence.append("Title specifies a specialist adjacent discipline not established strongly enough for automatic apply routing")

    blocker_codes = list(dict.fromkeys(blocker_codes))
    review_codes = list(dict.fromkeys(review_codes))

    methods = str(dimensions.get("methods") or "UNKNOWN").upper()
    language = str(dimensions.get("language") or "CLEAR").upper()
    mobility = str(dimensions.get("mobility") or "POTENTIALLY_VIABLE").upper()
    registration = str(dimensions.get("registration") or "CLEAR").upper()
    contract = str(dimensions.get("contract") or "UNKNOWN").upper()

    # Relevance is resolved before mobility/contract review. An obviously unrelated or
    # out-of-scope vacancy should not remain in REVIEW merely because sponsorship is unknown.
    if blocker_codes:
        recommendation = "SKIP"
        routing_reason = "Calibrated explicit out-of-scope, unrelated-domain, or hard-blocker evidence takes precedence."
    elif detail_missing:
        recommendation = "REVIEW"
        routing_reason = "Full JD/detail evidence is missing; calibrated routing remains fail-open."
    elif role_family == "OUT_OF_SCOPE":
        recommendation = "SKIP"
        routing_reason = "The title is explicitly outside the target career-stage families."
    elif scientific == "WEAK":
        recommendation = "SKIP" if unrelated_code else "LOW_PRIORITY"
        routing_reason = "Scientific fit is weak after calibrated title/domain matching."
    elif scientific == "UNCLEAR":
        if role_family == "UNKNOWN":
            recommendation = "SKIP"
            routing_reason = "Full details contain no reliable scientific anchor and the role itself is not a target family."
        elif role_family in PRIMARY_FAMILIES or role_family in SECONDARY_FAMILIES or role_family == "OTHER_RESEARCH":
            recommendation = "LOW_PRIORITY"
            routing_reason = "The role is potentially in scope, but the full posting contains no reliable profile-specific scientific anchor."
        else:
            recommendation = "REVIEW"
            routing_reason = "Scientific fit or role scope remains genuinely ambiguous."
    elif scientific == "ADJACENT" or specialist_review:
        recommendation = "REVIEW"
        routing_reason = "The vacancy is adjacent/specialist relative to the profile and requires human review."
    elif role_status in {"SECONDARY", "CONDITIONAL", "AMBIGUOUS"} or level in {"REVIEW", "UNKNOWN"}:
        recommendation = "REVIEW"
        routing_reason = "Scientific fit is plausible, but role family or level is not sufficiently established."
    elif any(value in {"REVIEW", "BLOCKED", "VERIFY_CURRENT_RULES"} for value in [methods, language, mobility, registration]):
        recommendation = "REVIEW"
        routing_reason = "A material non-scientific dimension still requires review."
    elif review_codes:
        recommendation = "REVIEW"
        routing_reason = "A configured non-scientific review signal remains unresolved."
    elif role_family == "POSTDOC" and scientific == "STRONG" and level == "STRONG":
        recommendation = "STRONG_APPLY"
        routing_reason = "Postdoctoral role with multiple/direct core scientific anchors and no unresolved material review signal."
    elif role_family in PRIMARY_FAMILIES and scientific in {"STRONG", "GOOD"} and level in {"STRONG", "ACCEPTABLE"}:
        recommendation = "APPLY"
        routing_reason = "Primary role with direct calibrated scientific fit and acceptable career-level fit."
    else:
        recommendation = "LOW_PRIORITY"
        routing_reason = "No blocker, but calibrated evidence does not support automatic apply routing."

    evidence["calibration"] = calibration_evidence
    fit_signals = list(dict.fromkeys(scientific_evidence + calibration_evidence))
    result = copy.deepcopy(base)
    result.update(
        {
            "evaluator_version": EVALUATOR_VERSION,
            "base_evaluator_version": base.get("evaluator_version") or "E0.1",
            "recommendation": recommendation,
            "role_family": role_family,
            "role_policy_status": role_status,
            "dimensions": dimensions,
            "fit_signals": fit_signals,
            "review_codes": review_codes,
            "blocker_codes": blocker_codes,
            "evidence": evidence,
            "reason": (
                f"{routing_reason} Calibrated dimensions: scientific={scientific}, level={level}, "
                f"methods={methods}, language={language}, mobility={mobility}, registration={registration}, contract={contract}."
            ),
        }
    )
    if blocker_codes or recommendation == "SKIP":
        result["pre_evaluation_disposition"] = "POLICY_SKIP"
    elif detail_missing:
        result["pre_evaluation_disposition"] = "NEEDS_DETAIL_REVIEW"
    elif review_codes or recommendation == "REVIEW":
        result["pre_evaluation_disposition"] = "POLICY_REVIEW"
    else:
        result["pre_evaluation_disposition"] = "ELIGIBLE_FOR_EVALUATION"
    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
