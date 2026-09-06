from __future__ import annotations

import copy
import re
import unicodedata
from datetime import date, datetime
from typing import Any

from src.evaluation.calibrated_e021 import evaluate_calibrated as evaluate_e021

EVALUATOR_VERSION = "E0.4_EVIDENCE_GATED_CANDIDATE"
GOOD_DETAIL = {"FULL", "PARTIAL"}
ACTIONABLE = {"STRONG_APPLY", "APPLY", "REVIEW"}

TARGET_ROLE = re.compile(
    r"\b(?:postdoc|post-doc|postdoctoral|post-doctoral|research fellow|research associate|research scientist|"
    r"assistant professor|lecturer|tenure[- ]track|junior professor|juniorprofessor|scientific project manager|"
    r"research project manager|research programme manager|grant manager|research funding manager)\b",
    re.I,
)
FACULTY_ROLE = re.compile(
    r"\b(?:assistant professor|tenure[- ]track professor|junior professor|juniorprofessor|lecturer|lect\.?\s+assist\.?\s+prof\.?)\b",
    re.I,
)
SENIOR_ROLE = re.compile(
    r"\b(?:associate professor|full professor|professor in|professor of|chair in|head of department|group leader)\b",
    re.I,
)
STUDENT_ROLE = re.compile(
    r"\b(?:phd position|phd student|phd researcher|doctoral student|doctoral candidate|doctoral researcher|doctoral training)\b",
    re.I,
)

DIRECT_CORE = re.compile(
    r"\b(?:exercise physiology|exercise science|sport(?:s)? science|sport and exercise|physical activity|"
    r"kinesiology|human movement|clinical exercise|exercise intervention|exercise training|aerobic exercise|"
    r"resistance training|sports medicine|exercise neuroscience|psychophysiolog(?:y|ical)|psychosocial stress|"
    r"psychological stress|stress recovery|stress response|stress biology|cortisol|hpa(?:-| )axis|brain health|"
    r"neurocognitive health)\b",
    re.I,
)
ADJACENT_SCIENCE = re.compile(
    r"\b(?:cognitive neuroscience|affective neuroscience|social neuroscience|neuroscience|brain ageing|brain aging|"
    r"connectomics?|digital health|behavio(?:u)?ral medicine|mental health intervention|healthy ageing|healthy aging|"
    r"rehabilitation|health promotion|wearables?|microbiome|microbiota|gut[- ]brain|public health|population health|"
    r"health data science|epidemiolog(?:y|ical)|community health|urban health)\b",
    re.I,
)
SECONDARY_TRACK = re.compile(
    r"\b(?:grant manager|research funding manager|scientific project manager|research project manager|"
    r"research programme manager|research program manager|grant writing|research funding)\b",
    re.I,
)

UNRELATED_FACULTY = re.compile(
    r"\b(?:international law|law|legal|philosophy|developmental psychology|educational psychology|clinical psychology|"
    r"cultural studies|culturele studies|business management|inclusive management|marketing|accounting|finance|"
    r"mathematics|maths|civil engineering|electrical engineering|electronic engineering|infrastructure|transport systems|"
    r"pharmacy|fine arts|artistic practice|optometry|speech and language therapy|archaeology)\b",
    re.I,
)
COGNITIVE_NEURO_FACULTY = re.compile(r"\bcognitive neuroscience\b", re.I)

NONACADEMIC_PRACTITIONER = re.compile(
    r"\b(?:personal trainer|fitness trainer|sporttherapeut|sports? therapist|exercise therapist)\b",
    re.I,
)
NONACADEMIC_TECH = re.compile(r"\b(?:research engineer|ai researcher|machine learning engineer)\b", re.I)
ACADEMIC_CONTEXT = re.compile(
    r"\b(?:university|universit(?:y|at|ae?t)|college|faculty|school of|department|research institute|cnrs|academy)\b",
    re.I,
)
COMPANY_TECH_CONTEXT = re.compile(
    r"\b(?:database internals|compiler|distributed systems|parallel computing|query language|foundation models?|"
    r"deep learning|large language models?|llms?|hardware acceleration|computer vision)\b",
    re.I,
)

SPECIALIST_TERMS: dict[str, re.Pattern[str]] = {
    "ADVANCED_AI_ML": re.compile(
        r"\b(?:deep learning|foundation models?|multimodal model(?:ling|ing)|representation learning|"
        r"large language models?|llms?|reinforcement learning|advanced machine learning|neuroai)\b",
        re.I,
    ),
    "COMPUTATIONAL_NEURO": re.compile(
        r"\b(?:detailed biophysical modell?ing|computational neuroscience|high-density neural recordings?|"
        r"advanced signal processing)\b",
        re.I,
    ),
    "BIOINFORMATICS_OMICS": re.compile(
        r"\b(?:bioinformatics|multi-omics|multiomics|genomics|transcriptomics|rna-?seq|high-throughput sequencing|"
        r"computational biology)\b",
        re.I,
    ),
    "MOLECULAR_WETLAB": re.compile(
        r"\b(?:molecular biology|cellular biology|flow cytometry|bioconjugation|protein chemistry|oligonucleotide chemistry|"
        r"dna-encoded librar(?:y|ies)|aso biochemistry|patch clamp|optogenetics?)\b",
        re.I,
    ),
    "ELECTROPHYSIOLOGY": re.compile(r"\belectrophysiolog(?:y|ical)\b", re.I),
    "NEURODEGENERATION_MODELS": re.compile(
        r"\b(?:neurodegenerative disorders?|neurodegeneration|parkinson(?:'s)?|rodent models?|stereotaxic|"
        r"in vivo disease models?)\b",
        re.I,
    ),
    "CHEMISTRY_SPECIALIST": re.compile(
        r"\b(?:synthetic chemistry|medicinal chemistry|chemobio(?:logy|logical)|protein chemistry|biomolecular chemistry)\b",
        re.I,
    ),
}
REQUIRED_CUE = re.compile(
    r"\b(?:required|essential|must have|must hold|strong expertise|strong background|demonstrated expertise|"
    r"demonstrable expertise|proven experience|extensive experience|successful candidate (?:will|should) have|"
    r"applicants? (?:must|should) have|you (?:must|should) have)\b",
    re.I,
)
PREFERRED_CUE = re.compile(
    r"\b(?:preferred|preferably|desirable|desired|advantage(?:ous)?|would be an asset|is a plus|are a plus|valued)\b",
    re.I,
)

PROTECTED_ELIGIBILITY = re.compile(
    r"\b(?:only open to|open to .{0,80} only|identified position|genuine occupational requirement)\b.{0,180}"
    r"\b(?:aboriginal|torres strait islander|indigenous|first nations)\b|"
    r"\b(?:aboriginal|torres strait islander|indigenous|first nations)\b.{0,180}"
    r"\b(?:only|identified position|genuine occupational requirement)\b",
    re.I,
)

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_PATTERN = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
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
    evidence["e04"] = _append(list(evidence.get("e04") or []), reason)
    out["evidence"] = evidence
    return out


def _review(result: dict[str, Any], code: str, reason: str, *, scientific: str | None = None) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["recommendation"] = "REVIEW"
    out["pre_evaluation_disposition"] = "POLICY_REVIEW"
    out["review_codes"] = _append(list(out.get("review_codes") or []), code)
    if scientific:
        dims = copy.deepcopy(out.get("dimensions") or {})
        dims["scientific"] = scientific
        out["dimensions"] = dims
    out["reason"] = reason + " " + str(out.get("reason") or "")
    evidence = copy.deepcopy(out.get("evidence") or {})
    evidence["e04"] = _append(list(evidence.get("e04") or []), reason)
    out["evidence"] = evidence
    return out


def _parse_iso(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _observed(job: dict[str, Any]) -> date | None:
    for value in (
        (job.get("source") or {}).get("retrieved_at"),
        (job.get("raw_extra") or {}).get("observed_at"),
    ):
        parsed = _parse_iso(value)
        if parsed:
            return parsed
    return None


def _deadline(job: dict[str, Any]) -> date | None:
    structured = _parse_iso((job.get("dates") or {}).get("deadline_at"))
    if structured:
        return structured
    text = _jd(job)
    label = r"(?:application deadline|closing date|close date|closes|bewerbungsfrist)"
    match = re.search(
        rf"\b{label}\b\s*[:\-]?\s*(\d{{1,2}})(?:st|nd|rd|th)?[\s./-]+({_MONTH_PATTERN})[\s,./-]+(20\d{{2}})\b",
        text,
        re.I,
    )
    if match:
        month_text = match.group(2).lower()
        month = _MONTHS.get(month_text) or _MONTHS.get(month_text[:3])
        if month:
            try:
                return date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                return None
    return None


def _sentence_windows(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?;])\s+|\n+", text) if part.strip()]


def _required_specialist(text: str) -> str | None:
    """Return a specialist capability only when the same local sentence is mandatory.

    E0.3 overblocked desirable/preferred expertise because broad character windows could
    mix a preferred cue from one requirement with a mandatory cue from another. E0.4
    deliberately reasons at sentence/bullet granularity and lets preferred language win.
    """
    for sentence in _sentence_windows(text):
        if PREFERRED_CUE.search(sentence):
            continue
        if not REQUIRED_CUE.search(sentence):
            continue
        for code, pattern in SPECIALIST_TERMS.items():
            if pattern.search(sentence):
                return code
    return None


def _explicit_degree_mismatch(text: str) -> str | None:
    patterns = {
        "COMPUTER_AI": r"\bph\.?d\.?\s+(?:in|within)\s+(?:computer science|artificial intelligence|data science|electrical engineering)\b",
        "IMMUNOLOGY": r"\bph\.?d\.?\s+(?:in|within)\s+immunolog(?:y|ical)\b",
        "CHEMISTRY": r"\bph\.?d\.?\s+(?:in|within)\s+(?:chemistry|chemical biology|medicinal chemistry)\b",
        "MATHEMATICS": r"\bph\.?d\.?\s+(?:in|within)\s+(?:mathematics|maths|statistics)\b",
        "ENGINEERING": r"\bph\.?d\.?\s+(?:in|within)\s+(?:civil engineering|geotechnical engineering|structural engineering)\b",
    }
    for code, pattern in patterns.items():
        m = re.search(pattern, text, re.I)
        if m:
            local = text[m.start():min(len(text), m.end() + 100)]
            if not re.search(r"\bor (?:a )?(?:closely )?related (?:field|discipline|area)\b", local, re.I):
                return code
    return None


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluate_e021(job))
    result["evaluator_version"] = EVALUATOR_VERSION
    result["base_calibrated_evaluator_version"] = "E0.2.1_CALIBRATED_SHADOW"

    title = _title(job)
    text = _jd(job)
    combined = f"{title} {text}"
    role_family = str(result.get("role_family") or "UNKNOWN").upper()
    detail_status = str((job.get("description") or {}).get("detail_status") or "NOT_ATTEMPTED").upper()
    substantive = detail_status in GOOD_DETAIL and len(text) >= 250

    observed = _observed(job)
    deadline = _deadline(job)
    if observed and deadline and deadline < observed:
        return _skip(result, "EXPLICIT_DEADLINE_PASSED_E04", "The explicit vacancy deadline is before the observation date.")

    if STUDENT_ROLE.search(title) and not re.search(r"\bpost[- ]?doc", title, re.I):
        return _skip(result, "OUT_OF_SCOPE_STUDENT_E04", "The title explicitly identifies a doctoral/student position rather than the target postdoctoral/faculty stage.")
    if SENIOR_ROLE.search(title) and not re.search(r"assistant professor", title, re.I):
        return _skip(result, "OUT_OF_SCOPE_SENIOR_E04", "The title identifies a senior faculty/group-leader appointment outside the configured target level.")

    direct = bool(DIRECT_CORE.search(combined))
    adjacent = bool(ADJACENT_SCIENCE.search(combined))
    secondary = bool(SECONDARY_TRACK.search(combined))

    if NONACADEMIC_PRACTITIONER.search(title):
        return _skip(result, "NON_ACADEMIC_PRACTITIONER_E04", "The vacancy is a practitioner/service role rather than a target academic research appointment.")
    if NONACADEMIC_TECH.search(title) and COMPANY_TECH_CONTEXT.search(text) and not ACADEMIC_CONTEXT.search(title):
        return _skip(result, "NON_ACADEMIC_TECH_RESEARCH_E04", "The role is an industry technology-research/engineering position centred on systems or advanced AI rather than the academic profile.")

    # Faculty appointments require discipline-level identity, not incidental keywords.
    if FACULTY_ROLE.search(title):
        if COGNITIVE_NEURO_FACULTY.search(title):
            return _review(
                result,
                "ADJACENT_COGNITIVE_NEURO_FACULTY_E04",
                "Cognitive-neuroscience faculty is adjacent to the research profile but requires discipline/methods-level human assessment before applying.",
                scientific="ADJACENT",
            )
        if UNRELATED_FACULTY.search(title) and not DIRECT_CORE.search(title):
            return _skip(result, "FACULTY_DISCIPLINE_MISMATCH_E04", "The named faculty discipline is outside the candidate's established academic field; incidental health/cognition terms do not establish appointment-level fit.")
        if adjacent and not direct:
            return _review(result, "ADJACENT_FACULTY_E04", "The faculty role is scientifically adjacent but not a direct discipline match; human review is required.", scientific="ADJACENT")

    specialist = _required_specialist(text)
    if specialist and not direct:
        return _skip(result, f"CENTRAL_{specialist}_E04", "A specialist capability outside the established profile is explicitly mandatory and central to this non-core vacancy.")

    degree_mismatch = _explicit_degree_mismatch(text)
    if degree_mismatch and not direct:
        return _skip(result, f"EXPLICIT_DEGREE_MISMATCH_{degree_mismatch}_E04", "The posting explicitly requires a specialist doctoral discipline not established by the candidate's Exercise Physiology PhD.")

    # Sensitive/protected eligibility is surfaced only for a scientifically plausible job;
    # the evaluator never infers the user's protected identity.
    if PROTECTED_ELIGIBILITY.search(text):
        if direct or adjacent or secondary:
            return _review(result, "PROTECTED_ELIGIBILITY_VERIFY_E04", "The vacancy has a protected-attribute eligibility restriction; eligibility must be verified by the user and is not inferred.")
        return _skip(result, "UNRELATED_WITH_PROTECTED_ELIGIBILITY_E04", "The vacancy is not scientifically relevant; no sensitive personal inference is needed to exclude it.")

    # High-precision clean-report gate. A generic research title without an actual profile
    # anchor is not useful REVIEW merely because role scope or sponsorship is uncertain.
    if not (direct or adjacent or secondary):
        if substantive or not TARGET_ROLE.search(title):
            return _skip(result, "NO_PROFILE_RELEVANCE_EVIDENCE_E04", "Neither the title nor substantive captured description provides a reliable scientific/secondary-track anchor to the profile.")
        return _skip(result, "INSUFFICIENT_RELEVANCE_EVIDENCE_E04", "The captured detail is incomplete and the title itself provides no profile-relevant scientific anchor; it is kept out of the clean review queue.")

    # Advanced/specialist themes that are only preferred/desirable remain reviewable when
    # the scientific topic itself is adjacent; they are not converted to hard blockers.
    if adjacent and not direct:
        return _review(result, "ADJACENT_SCIENTIFIC_FIT_E04", "The vacancy has a genuine adjacent scientific anchor but not enough direct profile fit for automatic application.", scientific="ADJACENT")
    if secondary and not direct:
        return _review(result, "SECONDARY_TRACK_E04", "The vacancy matches the configured grant/project-management secondary track and requires human review.")

    # Automatic apply is reserved for direct-core fit. Preserve an existing calibrated
    # direct recommendation only when no blocker remains; otherwise fail safely to review.
    recommendation = str(result.get("recommendation") or "REVIEW").upper()
    blockers = list(result.get("blocker_codes") or [])
    if direct and blockers:
        return _review(result, "DIRECT_FIT_WITH_UNRESOLVED_BLOCKER_E04", "Scientific fit is direct, but a material eligibility/method blocker remains unresolved.")
    if direct and recommendation in {"STRONG_APPLY", "APPLY"}:
        return result
    if direct:
        return _review(result, "DIRECT_FIT_REQUIRES_REVIEW_E04", "Direct scientific fit is present, but the lower-level evaluator did not establish a sufficiently clean automatic-apply case.", scientific="GOOD")

    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
