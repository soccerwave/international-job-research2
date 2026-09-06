from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any

from src.evaluation.evaluator import evaluate_vacancy

EVALUATOR_VERSION = "E1.0_RECALL_FIRST_CANDIDATE"
GOOD_DETAIL = {"FULL", "PARTIAL"}

# E1 is a separate architecture experiment, not E0.9. It keeps E0.1's
# recall-first philosophy but removes the assumption that every inherited E0.1
# blocker is safe. HIDDEN requires positive, independently understandable
# exclusion evidence. Absence of a recognised positive profile anchor is never
# by itself a reason to hide a vacancy.

_POSTDOC = re.compile(r"\b(?:post\s*-?\s*doc(?:toral)?|postdoctoral|post-doctoral)\b", re.I)
_STUDENT = re.compile(
    r"\b(?:ph\.?d\.?|doctoral)\s+(?:student|candidate|researcher|trainee|position|fellowship|programme|program|thesis)\b|"
    r"\bph\.?d\.?\s+students?\b|\bdoctoral\s+training\b|\bstudentische\s+mitarbeit\b",
    re.I,
)
_SENIOR = re.compile(
    r"\b(?:associate professor|full professor|senior lecturer|reader in|chair in|dean|head of school|head of department)\b|"
    r"\bprofessor\s+(?:in|of)\b",
    re.I,
)
_TARGET_TITLE = re.compile(
    r"\b(?:post\s*-?\s*doc(?:toral)?|research\s+fellow|research\s+associate|assistant\s+professor|"
    r"research\s+assistant\s+professor|lecturer|tenure\s*-?\s*track|junior\s+profess(?:or|orship)|"
    r"juniorprofessor|universit[aä]tsassistent.{0,20}postdoc|university\s+assistant.{0,20}postdoc)\b",
    re.I,
)
_SECONDARY_DISABLED = re.compile(
    r"\b(?:research scientist|scientific project manager|research project manager|research programme manager|research program manager)\b",
    re.I,
)
_NON_TARGET_IDENTITY = re.compile(
    r"\b(?:discipline librarian|librarian|business manager|executive director|accreditation(?: and quality)?(?: compliance)? officer|"
    r"programme coordinator|program coordinator|project coordinator|partnerships? and impact manager|principal enablement lead|"
    r"day nursery assistant|nursery assistant|teacher fellowship|personal trainer|fitness trainer|compEx trainer|"
    r"adjunct appointments?|practice lecturer|praktijk.?lector)\b",
    re.I,
)
_RESEARCH_SUPPORT = re.compile(
    r"\bresearch assistant\b(?!\s*/\s*research associate)|\bresearch technician\b|\bresearch support officer\b",
    re.I,
)

# Strong profile signals are intentionally narrower than all possible adjacency.
# They may prevent a broad discipline word from hiding a genuinely cross-domain
# role, but they are not required for a vacancy to remain visible.
_DIRECT_RELEVANT = re.compile(
    r"\b(?:exercise physiology|exercise science|sport(?:s)? science|sport and exercise|physical activity|"
    r"human movement|kinesiology|clinical exercise|exercise intervention|exercise training|sports medicine|"
    r"exercise neuroscience|psychophysiolog(?:y|ical)|psychosocial stress|psychological stress|stress biology|"
    r"stress recovery|cortisol|hpa(?:-| )axis|brain health|neurocognitive health|cognitive neuroscience|"
    r"public health|population health|epidemiolog(?:y|ical)|health data science|rehabilitation|healthy ag(?:e|ei)ing|"
    r"digital health|behavio(?:u)?ral medicine|quality of life)\b",
    re.I,
)

# Title-level discipline identity is positive evidence of non-fit. The relevant
# override uses only the strong signals above, not generic words such as health,
# cognition or wellbeing.
_UNRELATED_TITLE = re.compile(
    r"\b(?:law|legal studies?|criminolog(?:y|ist)|philosophy|marketing|accounting|finance|economics?|econometrics|"
    r"business(?: and)? management|social work|social care|public policy|politics|applied linguistics|"
    r"chemistry|chemical engineering|medicinal chemistry|polymer science|pharmacy|pharmaceutical formulation|"
    r"civil engineering|structural engineering|electrical engineering|electronic engineering|mechanical engineering|"
    r"timber engineering|power systems?|networked systems?|network science|computer science|cybersecurity|software engineering|"
    r"artificial intelligence|machine learning|robotics|control systems?|laser physics|quantum physics|quantum optics|"
    r"photonics?|radar systems?|nuclear reactors?|earth sciences?|geology|geoscience|hydrogeolog(?:y|ical)|hydrology|"
    r"agronomy|plant science|plant immunity|crop science|forest ecology|weed ecology|bioarts?|biomaterials?|"
    r"product-system design|inclusive management)\b",
    re.I,
)

# Some professional/discipline identities are outside the configured academic
# target even when they contain physiology/health language.
_PROFESSIONAL_NON_TARGET = re.compile(
    r"\b(?:chiropractic|chiropractor|sporttherapeut|sports? therapist|exercise therapist|huisarts|general practitioner)\b",
    re.I,
)

# Coherent full-JD domain clusters allow generic titles such as "Postdoctoral
# Researcher" to be excluded without relying on absence of relevance. At least
# two distinct high-specificity signals from one cluster are required.
_DOMAIN_CLUSTERS: dict[str, tuple[re.Pattern[str], ...]] = {
    "LAW_POLITICS": tuple(re.compile(p, re.I) for p in (
        r"\blegal doctrine\b", r"\bcommercial law\b", r"\binternational law\b", r"\bcriminolog(?:y|ical)\b",
        r"\bmilitary labour\b", r"\bpublic policy\b", r"\bpolitical science\b",
    )),
    "BUSINESS_ECON": tuple(re.compile(p, re.I) for p in (
        r"\bmarketing\b", r"\baccounting\b", r"\bcorporate finance\b", r"\beconometrics\b",
        r"\bbusiness management\b", r"\bsustainable business\b",
    )),
    "ENGINEERING_COMPUTING": tuple(re.compile(p, re.I) for p in (
        r"\bpower systems?\b", r"\bstructural engineering\b", r"\bcivil engineering\b", r"\belectrical engineering\b",
        r"\belectronic engineering\b", r"\btimber engineering\b", r"\bcontrol systems?\b", r"\bradar systems?\b",
        r"\bnetworked systems?\b", r"\bcomputer science\b", r"\bcybersecurity\b", r"\bsoftware engineering\b",
        r"\breinforcement learning\b", r"\bdeep learning\b",
    )),
    "PHYSICS_SPACE": tuple(re.compile(p, re.I) for p in (
        r"\blaser physics\b", r"\boptical frequency combs?\b", r"\bquantum physics\b", r"\bquantum optics\b",
        r"\bastrophysics\b", r"\bastronomy\b", r"\bspaceborne\b", r"\bcondensed matter\b",
    )),
    "CHEMISTRY_PHARMA": tuple(re.compile(p, re.I) for p in (
        r"\borganometallic\b", r"\bsynthetic chemistry\b", r"\bmedicinal chemistry\b", r"\bpolymer chemistry\b",
        r"\bpharmaceutical formulation\b", r"\boral lipid[- ]based formulations?\b", r"\bcatalysis\b",
    )),
    "EARTH_PLANT": tuple(re.compile(p, re.I) for p in (
        r"\bhydrogeolog(?:y|ical)\b", r"\bhydrology\b", r"\bearth materials?\b", r"\bgeoscience\b",
        r"\bplant immunity\b", r"\bplant breeding\b", r"\bcrop science\b", r"\bagronomy\b", r"\bforest ecology\b",
    )),
    "HUMANITIES_ARTS": tuple(re.compile(p, re.I) for p in (
        r"\bapplied linguistics\b", r"\bphilosophy\b", r"\bfine arts\b", r"\bartistic practice\b", r"\bbioarts?\b",
    )),
    "SPECIALIST_MOLECULAR": tuple(re.compile(p, re.I) for p in (
        r"\bmolecular biology\b", r"\bcell culture\b", r"\bflow cytometr(?:y|ic)\b", r"\bwestern blot\b",
        r"\bprotein biochemistry\b", r"\bsingle[- ]molecule biophysics\b", r"\bmRNA cancer immunotherapy\b",
    )),
}

_PREFERENCE = re.compile(
    r"\b(?:preferred|preferably|desirable|desired|advantage(?:ous)?|would be an asset|is a plus|not required|"
    r"w[uü]nschenswert|erw[uü]nscht|idealerweise|von vorteil)\b",
    re.I,
)
_MANDATORY = re.compile(
    r"\b(?:required|essential|mandatory|must have|must hold|must possess|must be|need to have|"
    r"demonstrated expertise|demonstrable expertise|proven experience|strong experience|extensive experience|"
    r"vorausgesetzt|erforderlich|zwingend|muss|m[uü]ssen)\b",
    re.I,
)
_EXTERNAL_DETAIL = re.compile(
    r"(?:full\s+job\s+description\s+for\s+(?:further\s+)?details?\s+and\s+essential\s+requirements?|"
    r"(?:essential|selection)\s+(?:criteria|requirements?)\s+(?:are|is)\s+(?:available|provided)\s+(?:in|within)\s+(?:the\s+)?(?:attached|linked)?\s*(?:job\s+description|role\s+profile|pdf|document)|"
    r"(?:information|candidate|recruitment|application)\s+(?:pack|package|brief)\b.{0,180}\b(?:full\s+details?|selection\s+criteria|essential\s+requirements?)\b|"
    r"\b(?:full|complete)\s+(?:selection\s+criteria|essential\s+criteria|person\s+specification)\b.{0,120}\b(?:see|available|download|attached|link|package|pack|document|pdf)\b)",
    re.I | re.S,
)


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def _title(job: dict[str, Any]) -> str:
    p = job.get("position") or {}
    return _norm(p.get("title_raw") or p.get("title_normalized") or "")


def _jd(job: dict[str, Any]) -> str:
    return _norm((job.get("description") or {}).get("full_jd") or "")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", text) if s.strip()]


def _mandatory_subject(text: str, subject: re.Pattern[str]) -> bool:
    for sentence in _sentences(text):
        if not subject.search(sentence):
            continue
        if _PREFERENCE.search(sentence):
            continue
        if _MANDATORY.search(sentence):
            return True
    return False


def _mandatory_german(text: str) -> bool:
    german = re.compile(r"\b(?:german|deutsch(?:kenntnisse)?)\b", re.I)
    level = re.compile(r"\b(?:c1|c2)\b", re.I)
    for sentence in _sentences(text):
        if not german.search(sentence):
            continue
        if _PREFERENCE.search(sentence):
            continue
        if _MANDATORY.search(sentence) or level.search(sentence):
            return True
    return False


def _au_work_rights_block(job: dict[str, Any], text: str) -> bool:
    country = str((job.get("location") or {}).get("country_code") or "").upper()
    if country != "AU":
        return False
    no_sponsor = re.search(
        r"\b(?:no (?:visa )?sponsorship|(?:visa )?sponsorship (?:is )?(?:not available|unavailable|not offered)|"
        r"cannot sponsor|unable to sponsor)\b",
        text,
        re.I,
    )
    rights = re.search(
        r"\b(?:must|required to|need to)\s+(?:already\s+)?(?:have|hold|possess).{0,100}(?:unrestricted|full|existing|current).{0,70}(?:australian\s+)?work rights?\b|"
        r"\b(?:unrestricted|full|existing|current).{0,70}(?:australian\s+)?work rights?.{0,80}(?:required|essential|must)\b",
        text,
        re.I | re.S,
    )
    return bool(no_sponsor and rights)


def _safe_mandatory_blocker(job: dict[str, Any], text: str) -> str | None:
    registration = re.compile(
        r"\b(?:professional registration|clinical registration|medical registration|nursing registration|ahpra|hcpc|gmc|nmc|coru)\b",
        re.I,
    )
    med_degree = re.compile(
        r"\b(?:medical degree|degree in medicine|mbbs|md degree|medical qualification|nursing degree|degree in nursing|registered nurse qualification)\b",
        re.I,
    )
    if _mandatory_subject(text, registration):
        return "MANDATORY_PROFESSIONAL_REGISTRATION_E1"
    if _mandatory_subject(text, med_degree):
        return "MANDATORY_MEDICAL_OR_NURSING_DEGREE_E1"

    for code, pattern in (
        ("MANDATORY_PATCH_CLAMP_E1", re.compile(r"\bpatch[- ]clamp\b", re.I)),
        ("MANDATORY_OPTOGENETICS_E1", re.compile(r"\boptogenetic(?:s)?\b", re.I)),
        ("MANDATORY_ELECTROPHYSIOLOGY_E1", re.compile(r"\belectrophysiolog(?:y|ical)\b", re.I)),
    ):
        if _mandatory_subject(text, pattern):
            return code

    wet = [
        re.compile(r"\bcell culture\b", re.I),
        re.compile(r"\bwestern blot\b", re.I),
        re.compile(r"\bflow cytometr(?:y|ic)\b", re.I),
        re.compile(r"\bmolecular biology\b", re.I),
        re.compile(r"\bcloning\b", re.I),
        re.compile(r"\bimmunoprecipitation\b", re.I),
    ]
    if sum(1 for p in wet if _mandatory_subject(text, p)) >= 2:
        return "MANDATORY_SPECIALIST_WET_LAB_E1"

    ai_terms = [
        re.compile(r"\bmachine learning\b", re.I),
        re.compile(r"\bdeep learning\b", re.I),
        re.compile(r"\bartificial intelligence\b", re.I),
        re.compile(r"\breinforcement learning\b", re.I),
        re.compile(r"\bcomputer vision\b", re.I),
    ]
    mandatory_ai = any(_mandatory_subject(text, p) for p in ai_terms)
    central_ai = sum(bool(p.search(text[:6500])) for p in ai_terms) >= 2
    if mandatory_ai and central_ai:
        return "MANDATORY_ADVANCED_AI_ML_E1"

    if _mandatory_german(text):
        return "MANDATORY_GERMAN_E1"
    if _au_work_rights_block(job, text):
        return "AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED_E1"
    return None


def _coherent_unrelated_cluster(title: str, text: str) -> str | None:
    # A strong direct title signal prevents generic cross-disciplinary wording
    # from being used as a hide rule. For generic titles, two distinct coherent
    # domain signals in the substantive posting are required.
    if _DIRECT_RELEVANT.search(title):
        return None
    front = f"{title} {text[:6500]}"
    for name, patterns in _DOMAIN_CLUSTERS.items():
        distinct = sum(bool(p.search(front)) for p in patterns)
        if distinct >= 2:
            return name
    return None


def _result(base: dict[str, Any], *, route: str, code: str, reason: str) -> dict[str, Any]:
    out = copy.deepcopy(base)
    out["evaluator_version"] = EVALUATOR_VERSION
    out["base_evaluator_version"] = str(base.get("evaluator_version") or "E0.1")
    out["operational_route"] = route
    out["needs_detail_review"] = route == "NEEDS_DETAIL_REVIEW"
    out["e1_codes"] = [code]
    if route == "HIDDEN":
        out["recommendation"] = "SKIP"
        out["pre_evaluation_disposition"] = "POLICY_SKIP"
    elif route == "NEEDS_DETAIL_REVIEW":
        out["recommendation"] = "REVIEW"
        out["pre_evaluation_disposition"] = "NEEDS_DETAIL_REVIEW"
    else:
        rec = str(base.get("recommendation") or "REVIEW").upper()
        out["recommendation"] = rec if rec in {"STRONG_APPLY", "APPLY", "REVIEW"} else "REVIEW"
        out["pre_evaluation_disposition"] = "POLICY_REVIEW" if out["recommendation"] == "REVIEW" else "ELIGIBLE_FOR_EVALUATION"
    out["reason"] = reason + " " + str(base.get("reason") or "")
    evidence = copy.deepcopy(base.get("evidence") or {})
    evidence["e1"] = {"route": route, "code": code, "reason": reason}
    out["evidence"] = evidence
    return out


def evaluate_recall_first(job: dict[str, Any]) -> dict[str, Any]:
    base = copy.deepcopy(evaluate_vacancy(job))
    title = _title(job)
    text = _jd(job)
    detail_status = str((job.get("description") or {}).get("detail_status") or "NOT_ATTEMPTED").upper()
    substantive_detail = detail_status in GOOD_DETAIL and bool(text)

    # 1. Career-stage and role-identity exclusions that are explicit in the title.
    if _STUDENT.search(title) and not _POSTDOC.search(title):
        return _result(base, route="HIDDEN", code="EXPLICIT_STUDENT_ROLE_E1", reason="The vacancy title explicitly identifies a doctoral/student training role.")
    if _SENIOR.search(title) and not re.search(r"\b(?:assistant|junior)\s+professor\b|\bw\s*1\b", title, re.I):
        return _result(base, route="HIDDEN", code="EXPLICIT_SENIOR_STAGE_E1", reason="The vacancy title explicitly identifies a senior academic stage outside the configured target.")
    if _SECONDARY_DISABLED.search(title):
        return _result(base, route="HIDDEN", code="SECONDARY_ROLE_DISABLED_E1", reason="The title is an explicitly configured secondary role family, which is disabled by current policy.")
    if (_NON_TARGET_IDENTITY.search(title) or _RESEARCH_SUPPORT.search(title)) and not _TARGET_TITLE.search(title):
        return _result(base, route="HIDDEN", code="EXPLICIT_NON_TARGET_ROLE_E1", reason="The vacancy title explicitly identifies a non-target support, administrative, teaching-only or operational role.")
    if _PROFESSIONAL_NON_TARGET.search(title) and not _TARGET_TITLE.search(title):
        return _result(base, route="HIDDEN", code="EXPLICIT_NON_TARGET_PROFESSION_E1", reason="The title identifies a professional/practitioner role outside the configured academic research target.")

    # 2. Clear discipline identity in the title. This is positive non-fit evidence;
    # a generic lack of profile keywords is never used here.
    if _UNRELATED_TITLE.search(title) and not _DIRECT_RELEVANT.search(title):
        return _result(base, route="HIDDEN", code="EXPLICIT_UNRELATED_TITLE_E1", reason="The vacancy title itself establishes a scientific/academic discipline outside the declared profile.")

    # 3. Explicit mandatory eligibility/method requirements can hide even if an
    # external document is unavailable, because the exclusion is already proved.
    mandatory_block = _safe_mandatory_blocker(job, text)
    if mandatory_block:
        return _result(base, route="HIDDEN", code=mandatory_block, reason="The available vacancy text contains an explicit mandatory requirement that the declared profile does not establish.")

    # 4. Missing or delegated essential criteria is a separate operational state.
    if not substantive_detail or _EXTERNAL_DETAIL.search(text):
        return _result(base, route="NEEDS_DETAIL_REVIEW", code="ESSENTIAL_DETAIL_UNRESOLVED_E1", reason="Essential vacancy evidence is missing, failed, or delegated to an external document; scientific rejection is unsafe.")

    # 5. Generic target titles may still be positively shown to belong to a very
    # different field by multiple coherent JD signals. This is deliberately not
    # the inverse of a relevance matcher.
    cluster = _coherent_unrelated_cluster(title, text)
    if cluster:
        return _result(base, route="HIDDEN", code=f"COHERENT_UNRELATED_DOMAIN_{cluster}_E1", reason=f"The substantive vacancy text contains multiple coherent high-specificity signals for the unrelated domain {cluster}.")

    # 6. Recall-first default. If we cannot positively prove exclusion, keep the
    # opportunity visible. E0.1 LOW/UNCLEAR/SKIP caused only by soft relevance
    # logic is converted to human REVIEW rather than hidden.
    return _result(base, route="JOBS", code="FAIL_OPEN_VISIBLE_E1", reason="No independently decisive exclusion was established; recall-first policy keeps the vacancy visible for human review.")


def with_recall_first_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation_e1"] = evaluate_recall_first(job)
    return clone
