from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVALUATOR_VERSION = "E0.1"
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


@lru_cache(maxsize=None)
def _load_json(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def _clean_domain_text(text: str) -> str:
    t = _norm(text)
    noise = [
        r"equal opportunit(?:y|ies).{0,700}",
        r"regardless of.{0,500}(?:race|religion|gender|sex|sexual orientation|disability|age).{0,500}",
        r"without regard to.{0,500}(?:race|religion|gender|sex|sexual orientation|disability|age).{0,500}",
        r"mental health (?:support|benefits?|resources?)",
        r"health(?:care)? insurance",
        r"wellbeing benefits?",
        r"wellness benefits?",
        r"exercise (?:your|their|the) rights",
        r"employee assistance programme",
    ]
    for pattern in noise:
        t = re.sub(pattern, " ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def _flatten_text(job: dict[str, Any]) -> tuple[str, str, str]:
    position = job.get("position") or {}
    req = job.get("requirements") or {}
    desc = job.get("description") or {}
    title = _norm(position.get("title_raw") or position.get("title_normalized") or "")
    department = _norm(position.get("department") or "")
    parts = [
        title,
        department,
        position.get("institution_raw") or "",
        req.get("degree_text") or "",
        " ".join(req.get("degree_fields") or []),
        " ".join(req.get("methods_required") or []),
        " ".join(req.get("methods_preferred") or []),
        req.get("work_rights_text") or "",
        req.get("sponsorship_text") or "",
        req.get("professional_registration_text") or "",
        req.get("teaching_requirement_text") or "",
        " ".join((x.get("raw_text") or "") for x in (req.get("language_requirements") or [])),
        desc.get("full_jd") or "",
    ]
    full = _norm(" ".join(str(x) for x in parts if x))
    return title, department, _clean_domain_text(full)


def _contains_phrase(text: str, phrase: str) -> bool:
    p = _norm(phrase)
    if not p:
        return False
    return p in text


def _unique_hits(text: str, phrases: list[str]) -> list[str]:
    out: list[str] = []
    for phrase in phrases:
        if _contains_phrase(text, phrase) and phrase not in out:
            out.append(phrase)
    return out


def _snippet(text: str, pattern: str, width: int = 120) -> str | None:
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    start = max(0, m.start() - width)
    end = min(len(text), m.end() + width)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _explicit_requirement(text: str, subject_pattern: str) -> bool:
    requirement_words = r"(?:required|essential|mandatory|must have|must possess|demonstrated expertise|strong experience|proven experience|extensive experience)"
    return bool(
        re.search(rf"{requirement_words}.{{0,100}}(?:{subject_pattern})", text, re.I)
        or re.search(rf"(?:{subject_pattern}).{{0,100}}{requirement_words}", text, re.I)
    )


def _role_detection(job: dict[str, Any], title: str, text: str) -> tuple[str, str, list[str]]:
    roles = _load_json("roles.json")
    country = ((job.get("location") or {}).get("country_code") or "").upper()
    existing = ((job.get("position") or {}).get("role_family") or "UNKNOWN").upper()
    evidence: list[str] = []

    if re.search(r"\b(?:phd|doctoral)\s+(?:student|candidate|trainee)\b|\bdoctoral researcher\b", title, re.I) and "postdoc" not in title:
        return "OUT_OF_SCOPE", "OUT_OF_SCOPE", ["Title explicitly identifies a doctoral/student role"]

    if country == "FR" and re.search(r"\b(?:maitre de conferences|mcf)\b", title, re.I):
        return "OUT_OF_SCOPE", "OUT_OF_SCOPE", ["French faculty title is explicitly outside the current market policy"]

    if existing not in {"", "UNKNOWN"}:
        if existing in PRIMARY_FAMILIES:
            status = "PRIMARY"
        elif existing in SECONDARY_FAMILIES:
            status = "SECONDARY"
        elif existing == "OUT_OF_SCOPE":
            status = "OUT_OF_SCOPE"
        else:
            status = "CONDITIONAL"
        evidence.append(f"Collector/canonical role family: {existing}")
        return existing, status, evidence

    candidates: list[dict[str, str]] = []
    candidates.extend(roles.get("country_rules", {}).get(country, []))
    candidates.extend(roles.get("global_title_patterns", []))
    for rule in candidates:
        pattern = _norm(rule.get("pattern"))
        if pattern and pattern in title:
            family = rule.get("family", "UNKNOWN")
            policy = rule.get("policy", "CONDITIONAL")
            status = "PRIMARY" if policy in {"PRIMARY", "HIGH_VALUE"} else "CONDITIONAL"
            if policy in {"HARD_EXCLUDE", "NORMALLY_SKIP"}:
                status = "OUT_OF_SCOPE"
            if policy == "SECONDARY":
                status = "SECONDARY"
            evidence.append(f"Title matched role pattern: {rule.get('pattern')}")
            if family == "RESEARCH_FELLOW_POSTDOC":
                if re.search(r"\bpostdoc(?:toral)?\b|\bphd\b.{0,80}(?:required|essential)|(?:required|essential).{0,80}\bphd\b", text, re.I):
                    status = "PRIMARY"
                    evidence.append("Research Fellow has postdoctoral/PhD-level evidence")
                else:
                    status = "CONDITIONAL"
            return family, status, evidence

    if re.search(r"\b(?:full professor|professor of|chair in|associate professor)\b", title, re.I) and not re.search(r"assistant professor", title, re.I):
        return "OUT_OF_SCOPE", "OUT_OF_SCOPE", ["Senior professor role is outside the primary early-career faculty target"]

    if re.search(r"\bresearch fellow\b", title, re.I):
        return "RESEARCH_FELLOW_POSTDOC", "CONDITIONAL", ["Generic Research Fellow title requires level review"]

    if re.search(r"\bresearch(?:er)?\b|\bscientist\b", title, re.I):
        return "OTHER_RESEARCH", "CONDITIONAL", ["Research title detected but level is not safely normalized"]

    return "UNKNOWN", "AMBIGUOUS", ["No reliable role-family pattern detected"]


def _scientific_dimension(title: str, department: str, text: str) -> tuple[str, list[str], list[str], str | None]:
    profile = _load_json("scientific_profile.json")
    tracks = profile.get("scientific_tracks", {})
    core_terms = list(tracks.get("A_CORE_EXERCISE_PHYSICAL_ACTIVITY", [])) + list(
        tracks.get("B_CORE_EXERCISE_NEUROSCIENCE_STRESS", [])
    )
    adjacent_terms = list(tracks.get("C_ADJACENT", []))
    core_hits = _unique_hits(text, core_terms)
    adjacent_hits = _unique_hits(text, adjacent_terms)
    title_dept = f"{title} {department}".strip()
    title_core = _unique_hits(title_dept, core_terms)
    title_adjacent = _unique_hits(title_dept, adjacent_terms)
    evidence: list[str] = []
    review: list[str] = []

    if core_hits:
        evidence.append("Core scientific signals: " + ", ".join(core_hits[:8]))
    if adjacent_hits:
        evidence.append("Adjacent scientific signals: " + ", ".join(adjacent_hits[:6]))
    if title_core:
        evidence.append("Core title/department signal: " + ", ".join(title_core[:4]))

    unrelated_clusters = {
        "CHEMISTRY_MATERIALS": ["organometallic", "synthetic chemistry", "catalysis", "materials chemistry", "polymer chemistry"],
        "ASTRONOMY_ASTROPHYSICS": ["astronomy", "astrophysics", "observatory", "galaxy", "stellar"],
        "ENGINEERING_INFRASTRUCTURE": ["civil engineering", "structural engineering", "power systems", "electrical engineering", "construction engineering"],
        "BUSINESS_LAW": ["marketing", "accounting", "corporate finance", "commercial law", "legal research"],
        "AGRICULTURE_PLANT": ["plant breeding", "crop science", "agronomy", "horticulture", "plant pathology"],
    }
    unrelated: str | None = None
    if not core_hits and not adjacent_hits:
        for name, terms in unrelated_clusters.items():
            hits = _unique_hits(text, terms)
            title_hits = _unique_hits(title_dept, terms)
            if len(hits) >= 2 or (title_hits and len(hits) >= 1):
                unrelated = name
                evidence.append(f"High-confidence unrelated-domain cluster: {name} ({', '.join(hits[:4])})")
                break

    if len(core_hits) >= 3 or (title_core and len(core_hits) >= 2):
        return "STRONG", evidence, review, unrelated
    if core_hits:
        return "GOOD", evidence, review, unrelated
    if adjacent_hits or title_adjacent:
        return "ADJACENT", evidence, review, unrelated
    if unrelated:
        return "WEAK", evidence, review, unrelated
    review.append("UNCLEAR_DOMAIN")
    return "UNCLEAR", evidence, review, None


def _level_dimension(role_family: str, role_status: str, text: str) -> tuple[str, list[str], list[str]]:
    evidence: list[str] = []
    review: list[str] = []
    if role_family == "POSTDOC":
        return "STRONG", ["Postdoctoral level directly matches current career stage"], review
    if role_family == "RESEARCH_FELLOW_POSTDOC":
        if role_status == "PRIMARY":
            return "STRONG", ["Research Fellow has postdoctoral-level evidence"], review
        review.append("GENERIC_RESEARCH_FELLOW")
        return "REVIEW", ["Research Fellow level is not explicit enough"], review
    if role_family in {"ASSISTANT_PROFESSOR", "LECTURER", "RESEARCH_ASSISTANT_PROFESSOR", "TENURE_TRACK", "JUNIOR_PROFESSOR"}:
        evidence.append("Early-faculty level is a target progression from the declared postdoctoral profile")
        if re.search(r"(?:minimum|at least)\s*(?:8|9|10|1[1-9]|[2-9][0-9])\s+years", text, re.I):
            review.append("VERY_SENIOR_EXPERIENCE_REQUIREMENT")
            return "REVIEW", evidence + ["Posting states a very senior experience requirement"], review
        return "ACCEPTABLE", evidence, review
    if role_family in SECONDARY_FAMILIES:
        review.append("SECONDARY_ROLE_DISABLED_BY_DEFAULT")
        return "REVIEW", ["Secondary role family is not enabled for automatic apply routing"], review
    if role_family == "OUT_OF_SCOPE":
        return "MISMATCH", ["Role is outside the primary target level/scope"], review
    if role_family == "OTHER_RESEARCH":
        review.append("UNCERTAIN_LOCAL_TITLE")
        return "REVIEW", ["Research role level is not safely normalized"], review
    review.append("UNCERTAIN_LOCAL_TITLE")
    return "UNKNOWN", ["Role level could not be established"], review


def _candidate_method_match(term: str) -> bool:
    t = _norm(term)
    known_fragments = [
        "exercise", "physical activity", "fitness", "cardiorespiratory", "cpet", "randomized", "randomised",
        "intervention", "psychological", "cognitive", "cognition", "cortisol", "stress", "hpa", "nr3c1",
        "epigen", "physiolog", "mri", "neuroimaging", "statistics", "statistical", "spss", " r ", "project",
        "grant", "horizon", "msca", "digital health", "virtual reality", "wearable", "behavior", "behaviour",
    ]
    padded = f" {t} "
    return any(fragment in padded for fragment in known_fragments)


def _methods_dimension(job: dict[str, Any], text: str) -> tuple[str, list[str], list[str], list[str]]:
    req = job.get("requirements") or {}
    required = [_norm(x) for x in (req.get("methods_required") or []) if _norm(x)]
    preferred = [_norm(x) for x in (req.get("methods_preferred") or []) if _norm(x)]
    evidence: list[str] = []
    review: list[str] = []
    blockers: list[str] = []

    blocker_specs = [
        ("MANDATORY_PATCH_CLAMP", r"patch[- ]clamp"),
        ("MANDATORY_OPTOGENETICS", r"optogenetic"),
    ]
    for code, subject in blocker_specs:
        if _explicit_requirement(text, subject):
            blockers.append(code)
            snip = _snippet(text, subject)
            evidence.append(f"{code}: {snip or subject}")

    ai_subject = r"(?:advanced )?(?:machine learning|deep learning|artificial intelligence|computational modelling|computer vision)"
    if _explicit_requirement(text, ai_subject) and re.search(r"(?:python|pytorch|tensorflow|machine learning|deep learning|computer vision)", text, re.I):
        blockers.append("MANDATORY_ADVANCED_AI_ML")
        evidence.append("Advanced AI/ML/computational expertise is explicitly required and central")

    wet_lab_terms = [r"cell culture", r"western blot", r"flow cytometr", r"molecular biology", r"cloning", r"immunoprecipitation"]
    wet_required = [p for p in wet_lab_terms if _explicit_requirement(text, p)]
    if len(wet_required) >= 2:
        blockers.append("MANDATORY_SPECIALIST_WET_LAB")
        evidence.append("Multiple specialist wet-lab methods are explicitly mandatory")

    advanced_fmri = r"(?:advanced|independent|expert).{0,50}(?:fmri|neuroimaging).{0,50}(?:preprocess|analysis)|(?:fmri|neuroimaging).{0,50}(?:preprocess|analysis).{0,50}(?:advanced|expert|independent)"
    if re.search(advanced_fmri, text, re.I) and _explicit_requirement(text, r"(?:fmri|neuroimaging)"):
        review.append("ADVANCED_FMRI_ANALYSIS_NOT_ESTABLISHED")
        evidence.append("Advanced independent fMRI/neuroimaging analysis is required; profile only establishes exposure/collaboration")

    unknown_required = [x for x in required if not _candidate_method_match(x)]
    if unknown_required:
        review.append("METHOD_MISMATCH_UNCLEAR")
        evidence.append("Required methods not directly established in profile: " + ", ".join(unknown_required[:8]))

    matched_required = [x for x in required if _candidate_method_match(x)]
    if matched_required:
        evidence.append("Required methods aligned with profile: " + ", ".join(matched_required[:8]))
    if preferred:
        evidence.append("Preferred methods are non-blocking by policy: " + ", ".join(preferred[:6]))

    if blockers:
        return "MISMATCH", evidence, review, blockers
    if review:
        return "REVIEW", evidence, review, blockers
    if required and len(matched_required) == len(required):
        return "STRONG", evidence, review, blockers
    if required:
        return "ACCEPTABLE", evidence, review, blockers
    if preferred:
        return "ACCEPTABLE", evidence, review, blockers
    return "UNKNOWN", evidence, review, blockers


def _language_dimension(job: dict[str, Any], text: str) -> tuple[str, list[str], list[str], list[str]]:
    req = job.get("requirements") or {}
    evidence: list[str] = []
    review: list[str] = []
    blockers: list[str] = []
    teaching = _norm(req.get("teaching_requirement_text") or "")
    languages = req.get("language_requirements") or []

    german_c1_c2 = False
    for item in languages:
        language = _norm(item.get("language"))
        level = _norm(item.get("level"))
        mandatory = item.get("mandatory") is True
        raw = _norm(item.get("raw_text"))
        if language == "english":
            evidence.append("Academic English requirement is compatible with the declared profile")
            continue
        if language == "german" and mandatory and ("c1" in level or "c2" in level or "c1" in raw or "c2" in raw):
            if teaching or re.search(r"teach|teaching|lehre|unterricht", text, re.I):
                german_c1_c2 = True
                evidence.append("German C1/C2 is explicitly mandatory in a teaching context")
                continue
        if mandatory:
            review.append("LOCAL_LANGUAGE_MANDATORY_UNCONFIRMED")
            evidence.append(f"Mandatory local language not established in profile: {item.get('language')} {item.get('level') or ''}".strip())
        else:
            evidence.append(f"Preferred/non-mandatory local language is not a blocker: {item.get('language')}")

    if not languages:
        if re.search(r"german.{0,50}\b(?:c1|c2)\b|\b(?:c1|c2)\b.{0,50}german", text, re.I) and re.search(r"teach|teaching|lehre|unterricht", text, re.I) and _explicit_requirement(text, r"german"):
            german_c1_c2 = True
            evidence.append("German C1/C2 teaching requirement detected in Full JD")
        elif re.search(r"(?:fluent|native|bilingual|c1|c2).{0,40}(?:dutch|french|german)|(?:dutch|french|german).{0,40}(?:fluent|native|bilingual|c1|c2)", text, re.I) and _explicit_requirement(text, r"(?:dutch|french|german)"):
            review.append("LOCAL_LANGUAGE_MANDATORY_UNCONFIRMED")
            evidence.append("Mandatory local-language proficiency appears in Full JD and is not established in profile")

    if german_c1_c2:
        blockers.append("MANDATORY_GERMAN_C1_C2_TEACHING")
        return "BLOCKED", evidence, review, blockers
    if review:
        return "REVIEW", evidence, review, blockers
    return "CLEAR", evidence or ["No explicit incompatible language requirement detected"], review, blockers


def _mobility_dimension(job: dict[str, Any], text: str) -> tuple[str, list[str], list[str], list[str]]:
    policy = _load_json("mobility_policy.json")
    country = ((job.get("location") or {}).get("country_code") or "").upper()
    req = job.get("requirements") or {}
    sponsorship = _norm(req.get("sponsorship_text") or "")
    work_rights = _norm(req.get("work_rights_text") or "")
    combined = f"{sponsorship} {work_rights} {text}"
    country_policy = policy.get("countries", {}).get(country, {})
    status = country_policy.get("default_status", "VERIFY_CURRENT_RULES")
    evidence: list[str] = []
    review: list[str] = []
    blockers: list[str] = []

    sponsorship_yes = bool(re.search(r"(?:visa )?sponsorship (?:is )?(?:available|provided|offered)|eligible for sponsorship|we sponsor", combined, re.I))
    sponsorship_maybe = bool(re.search(r"sponsorship may be available|may consider sponsorship|sponsorship can be considered", combined, re.I))
    sponsorship_no = bool(re.search(r"no (?:visa )?sponsorship|sponsorship (?:is )?not available|cannot sponsor|unable to sponsor", combined, re.I))
    existing_rights = bool(re.search(r"must (?:already )?(?:have|hold).{0,70}(?:work rights|right to work|working rights)|existing unrestricted work rights|unrestricted working rights", combined, re.I))
    hosting = bool(re.search(r"hosting agreement", combined, re.I))

    if country == "AU" and sponsorship_no and existing_rights:
        blockers.append("AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED")
        evidence.append("Australia posting explicitly denies sponsorship and requires existing work rights")
        return "BLOCKED", evidence, review, blockers
    if sponsorship_yes or hosting:
        evidence.append("Posting contains positive sponsorship/hosting evidence")
        return "FAVORABLE", evidence, review, blockers
    if sponsorship_maybe:
        evidence.append("Posting says sponsorship may be available")
        return "POTENTIALLY_VIABLE", evidence, review, blockers
    if sponsorship_no:
        review.append("VISA_AMBIGUOUS")
        evidence.append("Posting says sponsorship is unavailable; independent/alternative route requires case review")
        return "REVIEW", evidence, review, blockers
    if existing_rights:
        review.append("WORK_RIGHTS_RESTRICTION")
        evidence.append("Posting contains an existing-work-rights restriction without a deterministic configured blocker")
        return "REVIEW", evidence, review, blockers
    if status == "REVIEW":
        review.append("SPONSORSHIP_UNSTATED")
        evidence.append(f"Mobility defaults to REVIEW for {country or 'unknown country'} when sponsorship is unstated")
    elif status == "VERIFY_CURRENT_RULES":
        review.append("VERIFY_CURRENT_MOBILITY_RULES")
        evidence.append("Mobility route must be current-verified for this market")
    else:
        evidence.append(f"No negative mobility evidence; policy default is {status}")
    return status, evidence, review, blockers


def _registration_dimension(job: dict[str, Any], text: str) -> tuple[str, list[str], list[str], list[str]]:
    req = job.get("requirements") or {}
    raw = _norm(req.get("professional_registration_text") or "")
    combined = f"{raw} {text}"
    evidence: list[str] = []
    review: list[str] = []
    blockers: list[str] = []

    if re.search(r"(?:registration|registered|licen[cs]e).{0,30}(?:preferred|desirable|advantage)", combined, re.I):
        return "CLEAR", ["Professional registration is preferred/desirable, not mandatory"], review, blockers
    mandatory_registration = bool(
        _explicit_requirement(combined, r"(?:professional registration|clinical registration|medical registration|nursing registration|ahpra|hcpc|gmc|nmc)")
        or re.search(r"must be (?:currently )?registered with|current registration with .{0,40}(?:is )?(?:required|essential)", combined, re.I)
    )
    if mandatory_registration:
        blockers.append("MANDATORY_PROFESSIONAL_REGISTRATION")
        evidence.append("Specific professional/clinical registration is explicitly mandatory and is not established in profile")
        return "BLOCKED", evidence, review, blockers
    if raw and re.search(r"registration|registered|licen[cs]e", raw, re.I):
        review.append("PROFESSIONAL_REGISTRATION_AMBIGUOUS")
        evidence.append("Professional-registration language is present but mandatory status is unclear")
        return "REVIEW", evidence, review, blockers
    return "CLEAR", ["No mandatory professional registration mismatch detected"], review, blockers


def _qualification_blockers(job: dict[str, Any], text: str) -> tuple[list[str], list[str]]:
    req = job.get("requirements") or {}
    degree_text = _norm(req.get("degree_text") or "")
    combined = f"{degree_text} {text}"
    blockers: list[str] = []
    evidence: list[str] = []
    medical = r"(?:medical degree|degree in medicine|mbbs|md degree|medical qualification)"
    nursing = r"(?:nursing degree|degree in nursing|registered nurse qualification)"
    if _explicit_requirement(combined, medical) or _explicit_requirement(combined, nursing):
        blockers.append("MANDATORY_MEDICAL_OR_NURSING_DEGREE")
        evidence.append("Medical or nursing degree is explicitly mandatory")
    return blockers, evidence


def _contract_dimension(job: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    contract = job.get("contract") or {}
    position = job.get("position") or {}
    term = (contract.get("term_type") or "UNKNOWN").upper()
    employment = (position.get("employment_type") or "UNKNOWN").upper()
    duration = contract.get("duration_months")
    evidence: list[str] = []
    review: list[str] = []

    if employment in {"CASUAL", "SESSIONAL"}:
        review.append("CASUAL_OR_SESSIONAL_ROLE")
        return "REVIEW", [f"Employment type is {employment}"], review
    if term in {"PERMANENT", "TENURE_TRACK"}:
        return "ATTRACTIVE", [f"Contract term is {term}"], review
    if term in {"FIXED_TERM", "TEMPORARY"}:
        if isinstance(duration, (int, float)) and duration < 12:
            review.append("SHORT_FIXED_TERM")
            return "REVIEW", [f"Fixed-term duration is {duration:g} months"], review
        return "ACCEPTABLE", [f"Contract term is {term}"], review
    return "UNKNOWN", ["Contract term is unknown; this is not a blocker"], review


def _existing_prepolicy(job: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    classification = job.get("classification") or {}
    disposition = classification.get("pre_evaluation_disposition") or "ELIGIBLE_FOR_EVALUATION"
    review = list(classification.get("review_codes") or [])
    blockers = list(classification.get("blocker_codes") or [])
    return disposition, review, blockers


def _route(
    *,
    role_status: str,
    scientific: str,
    level: str,
    methods: str,
    language: str,
    mobility: str,
    registration: str,
    contract: str,
    detail_missing: bool,
    review_codes: list[str],
    blocker_codes: list[str],
) -> tuple[str, str]:
    if blocker_codes:
        return "SKIP", "Explicit hard-blocker evidence takes precedence."
    if detail_missing:
        return "REVIEW", "Full JD/detail evidence is missing or failed; fail-open routing requires review."
    if any(x in {"REVIEW", "BLOCKED", "VERIFY_CURRENT_RULES"} for x in [methods, language, mobility, registration]):
        return "REVIEW", "At least one material non-scientific dimension requires review."
    if level in {"REVIEW", "UNKNOWN"} or scientific == "UNCLEAR":
        return "REVIEW", "Role level or scientific domain remains ambiguous."
    if role_status in {"SECONDARY", "CONDITIONAL", "AMBIGUOUS"}:
        return "REVIEW", "Role family is secondary/conditional/ambiguous under the current baseline."
    if scientific == "ADJACENT":
        return "REVIEW", "Adjacent scientific fit is retained for human review rather than automatically rejected."
    if scientific == "WEAK" or level == "MISMATCH":
        return "LOW_PRIORITY", "Fit is weak/outside primary level, but no explicit hard blocker justifies SKIP."
    if contract == "REVIEW":
        return "REVIEW", "Contract structure needs review even though it is not a hard blocker."
    if role_status == "PRIMARY" and scientific == "STRONG" and level == "STRONG" and methods in {"STRONG", "ACCEPTABLE", "UNKNOWN"}:
        return "STRONG_APPLY", "Primary postdoctoral role with strong scientific and level fit and no unresolved material blocker."
    if role_status == "PRIMARY" and scientific in {"STRONG", "GOOD"} and level in {"STRONG", "ACCEPTABLE"}:
        return "APPLY", "Primary role with good/strong scientific fit and acceptable career-level fit."
    if review_codes:
        return "REVIEW", "One or more configured review signals remain unresolved."
    return "LOW_PRIORITY", "No hard blocker, but the role does not meet the automatic apply routing criteria."


def evaluate_vacancy(job: dict[str, Any]) -> dict[str, Any]:
    title, department, text = _flatten_text(job)
    description = job.get("description") or {}
    detail_status = description.get("detail_status") or "NOT_ATTEMPTED"
    detail_missing = detail_status not in GOOD_DETAIL or not _norm(description.get("full_jd") or "")

    role_family, role_status, role_evidence = _role_detection(job, title, text)
    scientific, scientific_evidence, scientific_review, unrelated_cluster = _scientific_dimension(title, department, text)
    level, level_evidence, level_review = _level_dimension(role_family, role_status, text)
    methods, method_evidence, method_review, method_blockers = _methods_dimension(job, text)
    language, language_evidence, language_review, language_blockers = _language_dimension(job, text)
    mobility, mobility_evidence, mobility_review, mobility_blockers = _mobility_dimension(job, text)
    registration, registration_evidence, registration_review, registration_blockers = _registration_dimension(job, text)
    contract, contract_evidence, contract_review = _contract_dimension(job)
    qualification_blockers, qualification_evidence = _qualification_blockers(job, text)
    pre_disposition, existing_review, existing_blockers = _existing_prepolicy(job)

    blocker_codes = list(dict.fromkeys(existing_blockers + method_blockers + language_blockers + mobility_blockers + registration_blockers + qualification_blockers))
    review_codes = list(dict.fromkeys(existing_review + scientific_review + level_review + method_review + language_review + mobility_review + registration_review + contract_review))

    if role_family == "OUT_OF_SCOPE":
        if re.search(r"\b(?:phd|doctoral)\s+(?:student|candidate|trainee)\b|\bdoctoral researcher\b", title, re.I) and "postdoc" not in title:
            blocker_codes.append("ROLE_STUDENT")
        country = ((job.get("location") or {}).get("country_code") or "").upper()
        if country == "FR" and re.search(r"\b(?:maitre de conferences|mcf)\b", title, re.I):
            blocker_codes.append("FR_FACULTY_OUT_OF_SCOPE")

    if unrelated_cluster and scientific == "WEAK" and detail_status in GOOD_DETAIL:
        blocker_codes.append("HIGH_CONFIDENCE_UNRELATED_DOMAIN")

    if detail_missing:
        review_codes.append("FULL_JD_UNAVAILABLE")

    blocker_codes = list(dict.fromkeys(blocker_codes))
    review_codes = list(dict.fromkeys(review_codes))

    recommendation, routing_reason = _route(
        role_status=role_status,
        scientific=scientific,
        level=level,
        methods=methods,
        language=language,
        mobility=mobility,
        registration=registration,
        contract=contract,
        detail_missing=detail_missing,
        review_codes=review_codes,
        blocker_codes=blocker_codes,
    )

    if blocker_codes:
        final_disposition = "POLICY_SKIP"
    elif detail_missing:
        final_disposition = "NEEDS_DETAIL_REVIEW"
    elif review_codes or recommendation == "REVIEW":
        final_disposition = "POLICY_REVIEW"
    else:
        final_disposition = "ELIGIBLE_FOR_EVALUATION"

    fit_signals = list(dict.fromkeys(
        scientific_evidence
        + level_evidence
        + [x for x in method_evidence if "aligned" in x.lower() or "preferred" in x.lower()]
        + [x for x in language_evidence if "compatible" in x.lower()]
        + [x for x in mobility_evidence if "positive" in x.lower() or "no negative" in x.lower()]
        + [x for x in contract_evidence if "permanent" in x.lower() or "tenure" in x.lower()]
    ))

    evidence = {
        "role": role_evidence,
        "scientific": scientific_evidence,
        "level": level_evidence,
        "methods": method_evidence,
        "language": language_evidence,
        "mobility": mobility_evidence,
        "registration": registration_evidence,
        "qualification": qualification_evidence,
        "contract": contract_evidence,
    }

    reason = (
        f"{routing_reason} Dimensions: scientific={scientific}, level={level}, methods={methods}, "
        f"language={language}, mobility={mobility}, registration={registration}, contract={contract}."
    )

    return {
        "evaluator_version": EVALUATOR_VERSION,
        "recommendation": recommendation,
        "pre_evaluation_disposition": final_disposition,
        "role_family": role_family,
        "role_policy_status": role_status,
        "dimensions": {
            "scientific": scientific,
            "level": level,
            "methods": methods,
            "language": language,
            "mobility": mobility,
            "registration": registration,
            "contract": contract,
        },
        "fit_signals": fit_signals,
        "review_codes": review_codes,
        "blocker_codes": blocker_codes,
        "evidence": evidence,
        "reason": reason,
    }
