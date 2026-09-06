from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any

from src.evaluation.recall_first_e1 import evaluate_recall_first

EVALUATOR_VERSION = "E1.1_RECALL_FIRST_FINAL_CANDIDATE"

# Second and final deterministic recall-first architecture candidate. HIDDEN still
# requires positive exclusion evidence; missing positive-fit keywords never suffice.

_POSTDOC = re.compile(r"\b(?:post\s*-?\s*doc(?:toral)?|postdoctoral|post-doctoral)\b", re.I)
_TARGET_ROLE = re.compile(
    r"\b(?:post\s*-?\s*doc(?:toral)?|research\s+fellow|research\s+associate|assistant\s+professor|"
    r"research\s+assistant\s+professor|lecturer|tenure\s*-?\s*track|junior\s+profess(?:or|orship)|"
    r"juniorprofessor|w\s*1[- ]juniorprofessur|universit[aä]tsassistent.{0,20}postdoc|"
    r"university\s+assistant.{0,20}postdoc)\b", re.I,
)
_DIRECT_PROFILE_TITLE = re.compile(
    r"\b(?:exercise physiology|exercise science|sport(?:s)? science|sport and exercise|physical activity|"
    r"human movement|kinesiology|clinical exercise|exercise intervention|exercise training|sports medicine|"
    r"exercise neuroscience|psychophysiolog(?:y|ical)|psychosocial stress|psychological stress|stress biology|"
    r"stress recovery|cortisol|hpa(?:-| )axis|brain health|neurocognitive health|cognitive neuroscience|"
    r"public health|population health|epidemiolog(?:y|ical)|health data science|rehabilitation|"
    r"healthy ag(?:e|ei)ing|digital health|behavio(?:u)?ral medicine|quality of life)\b", re.I,
)
_STUDENT_STAGE = re.compile(
    r"\b(?:ph\.?d\.?\s*(?:offer|offers|scholarship|scholarships|position|positions|student|students|candidate|candidates|researcher|researchers)|"
    r"doctoral\s+(?:student|students|candidate|candidates|researcher|researchers|position|positions|training|programme|program)|"
    r"multiple\s+ph\.?d\.?\s+positions|fully[- ]funded\s+ph\.?d\.?\s+positions|"
    r"doktorand(?:in|innen|en)?|dissertationsstelle|promotionsstelle|promotionsstudent(?:in|en)?)\b", re.I,
)
_NON_TARGET_ROLE = re.compile(
    r"\b(?:school manager|business manager|operations manager|chief operating officer|executive director|"
    r"programme director|program director|education programme director|education program director|regional training hub|"
    r"student services officer|student services assistant|student success|student experience|engagement assistant|"
    r"administrative officer|administration officer|technical officer|scientific computing officer|compliance officer|"
    r"accreditation officer|quality compliance officer|partnerships? and impact manager|privacy manager|information manager|"
    r"enablement lead|auditor|research adviser|research advisor|project officer|research engineer|discipline librarian|librarian|"
    r"nursery assistant|teacher fellowship|personal trainer|fitness trainer|training hub|programme coordinator|program coordinator|"
    r"project coordinator|school administrator|faculty administrator)\b", re.I,
)
_FACULTY_OR_PROFESSIONAL_MISMATCH = re.compile(
    r"\b(?:clinical psychology|educational psychology|developmental psychology|nursing|midwifery|optometry|"
    r"speech and language therapy|speech-language therapy|palliative medicine|anaesthetics?|anesthesiology|respiratory medicine|"
    r"chiropractic|pharmacy|pharmaceutical sciences?|strategic management|entrepreneurship|public administration|"
    r"international development|facility\s*&?\s*hospitality|community services|inclusive management|english language teaching)\b", re.I,
)
_SPECIALIST_TITLE = re.compile(
    r"\b(?:immunologist|immunology|protein biochemistry|bioinformatics?|multi[- ]omics|genomics|population genomics|"
    r"rna biology|rna condensates?|cancer immunotherapy|autoantibod(?:y|ies)|nephropath(?:y|ies)|"
    r"oral lipid[- ]based formulations?|medicinal chemistry|organometallic|organom[eé]talliques?|photocatalysis|"
    r"biosensor development|physicist|neuromorphic systems?|quantum technolog(?:y|ies)|quantum sensing|"
    r"video compression|learned video compression|extreme ultraviolet|laser plasma|optical frequency combs?|"
    r"soil[- ]biomass|forest ecology|weed ecology|sea ice|small modular reactors?|spaceborne radar|"
    r"robotik|softwareentwicklung|chemische verfahrenstechnik|energie[- ] und distributionstechnik)\b", re.I,
)
_UNRELATED_TITLE = re.compile(
    r"\b(?:law|legal studies?|criminolog(?:y|ist)|philosophy|politics|political science|public policy|applied linguistics|"
    r"marketing|accounting|finance|economics?|econometrics|business administration|computer science|cybersecurity|"
    r"software engineering|networked systems?|network science|robotics|artificial intelligence|machine learning|"
    r"data science for soil|civil engineering|structural engineering|electrical engineering|electronic engineering|"
    r"mechanical engineering|power systems?|quantum physics|photonics?|laser physics|earth sciences?|geology|geoscience|"
    r"hydrology|agronomy|plant science|crop science|plant[- ]microbe|product-system design|bioarts?|biomaterials?)\b", re.I,
)
_IDENTIFIED_POSITION = re.compile(
    r"\b(?:identified\s+s?25|identified position|designated position|genuine occupational requirement)\b", re.I,
)
_PROTECTED_GROUP = re.compile(r"\b(?:aboriginal|torres strait islander|indigenous|first nations)\b", re.I)
_INVALID_TITLE = re.compile(r"^(?:retour en haut de page|back to top|home|jobs?|vacancies|search results?)$|^https?://", re.I)

_JD_CLUSTERS: dict[str, tuple[re.Pattern[str], ...]] = {
    "CLINICAL_PROFESSION": tuple(re.compile(p, re.I) for p in (
        r"\bclinical psychology\b", r"\bclinical practice\b", r"\bprofessional registration\b",
        r"\bregistered psychologist\b", r"\bmedical specialty\b", r"\bclinical training\b",
    )),
    "MOLECULAR_IMMUNOLOGY": tuple(re.compile(p, re.I) for p in (
        r"\bimmunolog(?:y|ical)\b", r"\bautoantibod(?:y|ies)\b", r"\bnephropath(?:y|ies)\b",
        r"\bprotein biochemistry\b", r"\brna biology\b", r"\bmRNA cancer immunotherapy\b",
        r"\bcell culture\b", r"\bflow cytometr(?:y|ic)\b", r"\bwestern blot\b",
    )),
    "OMICS_COMPUTATIONAL_BIO": tuple(re.compile(p, re.I) for p in (
        r"\bbioinformatics?\b", r"\bmulti[- ]omics\b", r"\bgenomics\b", r"\bpopulation genomics\b",
        r"\brna[- ]seq\b", r"\bcomputational biology\b", r"\bhigh[- ]throughput sequencing\b",
    )),
    "ENGINEERING_TECH": tuple(re.compile(p, re.I) for p in (
        r"\bbiosensor\b", r"\bvideo compression\b", r"\bneural representations?\b", r"\bnetworked systems?\b",
        r"\bpower systems?\b", r"\bradar systems?\b", r"\bsmall modular reactors?\b", r"\bpolymer recycling\b",
        r"\brobotics\b", r"\bsoftware engineering\b",
    )),
    "PHYSICS_CHEMISTRY": tuple(re.compile(p, re.I) for p in (
        r"\bextreme ultraviolet\b", r"\blaser plasma\b", r"\boptical frequency combs?\b", r"\bquantum sensing\b",
        r"\borganometallic\b", r"\borganom[eé]talliques?\b", r"\bphotocatalysis\b", r"\bluminescen(?:ce|t)\b",
        r"\bsolvent[- ]based recycling\b", r"\bpolymer(?:s| chemistry)?\b",
    )),
    "EARTH_ENVIRONMENT": tuple(re.compile(p, re.I) for p in (
        r"\bsea ice\b", r"\bsouthern ocean\b", r"\bsoil biomass\b", r"\bland use\b",
        r"\bforest ecology\b", r"\bearth materials?\b", r"\bhydrogeolog(?:y|ical)\b",
    )),
}


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower().replace("–", "-").replace("—", "-")).strip()


def _title(job: dict[str, Any]) -> str:
    p = job.get("position") or {}
    return _norm(p.get("title_raw") or p.get("title_normalized") or "")


def _subject_title(title: str) -> str:
    # ATS titles often append the organisational unit after the actual vacancy
    # subject, e.g. "Research Fellow - Evidence Synthesis, School of Nursing".
    # Faculty/school identity is context, not automatically the discipline of the
    # advertised role. Strip only a clear comma-delimited organisational suffix.
    return re.split(
        r",\s*(?:ucd\s+)?(?:school|faculty|department|college)\s+of\b",
        title,
        maxsplit=1,
        flags=re.I,
    )[0].strip()


def _jd(job: dict[str, Any]) -> str:
    return _norm((job.get("description") or {}).get("full_jd") or "")


def _hide(base: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
    out = copy.deepcopy(base)
    out.update({
        "evaluator_version": EVALUATOR_VERSION,
        "base_recall_first_version": str(base.get("evaluator_version") or "E1.0_RECALL_FIRST_CANDIDATE"),
        "operational_route": "HIDDEN",
        "needs_detail_review": False,
        "recommendation": "SKIP",
        "pre_evaluation_disposition": "POLICY_SKIP",
        "e11_codes": [code],
    })
    out["reason"] = reason + " " + str(base.get("reason") or "")
    evidence = copy.deepcopy(base.get("evidence") or {})
    evidence["e11"] = {"route": "HIDDEN", "code": code, "reason": reason}
    out["evidence"] = evidence
    return out


def _carry(base: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    out["evaluator_version"] = EVALUATOR_VERSION
    out["base_recall_first_version"] = str(base.get("evaluator_version") or "E1.0_RECALL_FIRST_CANDIDATE")
    out["e11_codes"] = ["E1_BASE_ROUTE_PRESERVED"]
    return out


def _coherent_jd_mismatch(subject_title: str, text: str) -> str | None:
    if _DIRECT_PROFILE_TITLE.search(subject_title):
        return None
    front = f"{subject_title} {text[:7000]}"
    for name, patterns in _JD_CLUSTERS.items():
        if sum(bool(p.search(front)) for p in patterns) >= 2:
            return name
    return None


def evaluate_recall_first_e11(job: dict[str, Any]) -> dict[str, Any]:
    base = evaluate_recall_first(job)
    title = _title(job)
    subject_title = _subject_title(title)
    text = _jd(job)
    combined = f"{title} {text[:8000]}"

    # Already-supported E1.0 explicit exclusions remain authoritative.
    if str(base.get("operational_route") or "").upper() == "HIDDEN":
        return _carry(base)

    if _INVALID_TITLE.search(title):
        return _hide(base, "INVALID_NON_VACANCY_TITLE_E11", "The extracted title is a URL/navigation/page artefact rather than a vacancy identity.")

    # Important: 'post-doctoral researcher' contains the substring 'doctoral researcher'.
    # It must never be mistaken for a student role.
    if _STUDENT_STAGE.search(title) and not _POSTDOC.search(title):
        return _hide(base, "EXPLICIT_STUDENT_STAGE_E11", "The title explicitly identifies a PhD/doctoral student or dissertation-stage position.")

    if _NON_TARGET_ROLE.search(title) and not _TARGET_ROLE.search(title):
        return _hide(base, "EXPLICIT_NON_TARGET_ROLE_E11", "The title explicitly identifies an administrative, support, operational, training or engineering role outside the configured academic target.")

    # Scientific/professional title exclusions operate on the vacancy subject, not
    # on a school/faculty suffix appended by an ATS.
    if _FACULTY_OR_PROFESSIONAL_MISMATCH.search(subject_title) and not _DIRECT_PROFILE_TITLE.search(subject_title):
        return _hide(base, "EXPLICIT_FACULTY_OR_PROFESSION_MISMATCH_E11", "The vacancy subject establishes a discipline or regulated profession outside the declared profile.")

    if _SPECIALIST_TITLE.search(subject_title) and not _DIRECT_PROFILE_TITLE.search(subject_title):
        return _hide(base, "EXPLICIT_SPECIALIST_DOMAIN_E11", "The vacancy subject explicitly identifies a specialist scientific/technical domain outside the declared profile.")

    if _UNRELATED_TITLE.search(subject_title) and not _DIRECT_PROFILE_TITLE.search(subject_title):
        return _hide(base, "EXPLICIT_UNRELATED_TITLE_E11", "The vacancy subject positively establishes an academic/scientific domain outside the declared profile.")

    if _IDENTIFIED_POSITION.search(combined) and _PROTECTED_GROUP.search(combined):
        return _hide(base, "PROTECTED_IDENTIFIED_POSITION_E11", "The vacancy is explicitly an identified/designated position restricted to a protected group not established by the candidate profile.")

    # Evidence insufficiency stays separate from scientific fit unless a title/eligibility
    # exclusion above was already decisive.
    if str(base.get("operational_route") or "").upper() == "NEEDS_DETAIL_REVIEW":
        return _carry(base)

    cluster = _coherent_jd_mismatch(subject_title, text)
    if cluster:
        return _hide(base, f"COHERENT_UNRELATED_DOMAIN_{cluster}_E11", f"The available posting contains multiple independent high-specificity signals for the unrelated domain {cluster}.")

    return _carry(base)


def with_recall_first_e11_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation_e11"] = evaluate_recall_first_e11(job)
    return clone
