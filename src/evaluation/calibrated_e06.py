from __future__ import annotations

import copy
import re
from typing import Any

from src.evaluation.calibrated_e04 import _jd, _title
from src.evaluation.calibrated_e05 import evaluate_calibrated as evaluate_e05

EVALUATOR_VERSION = "E0.6_BALANCED_RELEVANCE_CANDIDATE"

# E0.6 is a new candidate cycle. E0.5 remains immutable and rejected.
# Rules below target error classes exposed by E0.5's fresh blind set rather
# than canonical IDs. Ambiguous, plausibly relevant roles should surface for
# review; explicit policy blockers and discipline mismatches should not.

_TARGET_POSTDOC_RESEARCH = re.compile(
    r"\b(?:post\s*-?\s*doc(?:toral)?|postdoctoral|post-doctoral|research fellow|research associate|"
    r"research scientist|university assistant.{0,18}postdoc|universit[aä]tsassistent.{0,18}postdoc)\b",
    re.I,
)
_SENIOR_OUT_OF_STAGE = re.compile(
    r"\b(?:full professor|professor of |associate professor|senior lecturer|reader in|chair in|head of school|dean)\b",
    re.I,
)
_CLEAR_TITLE_DOMAIN_MISMATCH = re.compile(
    r"\b(?:business and management|business management|marketing|international law|law and|"
    r"neuromorphic systems?|electrical engineering|electronic engineering|computer engineering|"
    r"quantum physics|quantum optics|polymer chemistry|organic chemistry|organometallic chemistry|"
    r"hydrogeology|hydrology|timber engineering|plant immunity|plant science|cultural studies|fine arts)\b",
    re.I,
)

_HARD_POLICY_CODES = {
    "ROLE_STUDENT",
    "FR_FACULTY_OUT_OF_SCOPE",
    "MANDATORY_MEDICAL_OR_NURSING_DEGREE",
    "MANDATORY_PROFESSIONAL_REGISTRATION",
    "MANDATORY_GERMAN_C1_C2_TEACHING",
    "MANDATORY_PATCH_CLAMP",
    "MANDATORY_OPTOGENETICS",
    "MANDATORY_SPECIALIST_WET_LAB",
    "MANDATORY_ADVANCED_AI_ML",
    "AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED",
    "HIGH_CONFIDENCE_UNRELATED_DOMAIN",
}
_HARD_CODE_PREFIXES = (
    "MANDATORY_SPECIALIST_ADVANCED_AI_INFORMATICS_E05",
    "MANDATORY_SPECIALIST_STEM_CELL_TRANSPLANTATION_E05",
    "MANDATORY_SPECIALIST_ADVANCED_NEUROMODULATION_EPHYS_E05",
)

_PREFERENCE_CUE = re.compile(
    r"\b(?:preferred|preferably|desirable|desired|advantage(?:ous)?|would be an asset|is a plus|not required)\b",
    re.I,
)
_AU_NO_SPONSORSHIP = re.compile(
    r"\b(?:visa\s+)?sponsorship\s+(?:is\s+)?(?:not available|unavailable|not offered|not provided)|"
    r"\b(?:we|the university|the employer)\s+(?:cannot|can't|will not|won't|do not|does not)\s+(?:provide\s+)?(?:visa\s+)?sponsorship\b|"
    r"\bno\s+(?:visa\s+)?sponsorship\b",
    re.I,
)
_AU_WORK_RIGHTS_REQUIRED = re.compile(
    r"\b(?:must|required to|need to|will need to)\s+(?:already\s+)?(?:hold|have|possess)\b.{0,100}"
    r"\b(?:unrestricted|full|existing|current)\b.{0,70}\b(?:australian\s+)?work rights?\b|"
    r"\b(?:unrestricted|full|existing|current)\b.{0,70}\b(?:australian\s+)?work rights?\b.{0,80}\b(?:required|essential|must)\b",
    re.I | re.S,
)
_GERMAN = re.compile(r"\bgerman\b|\bdeutsch(?:kenntnisse)?\b", re.I)
_GERMAN_LEVEL_OR_MANDATE = re.compile(
    r"\b(?:c1|c2|mandatory|required|essential|must|vorausgesetzt|erforderlich|erfordernis)\b",
    re.I,
)
_OMICS = re.compile(r"\b(?:genomic(?:s| data)?|polygenic risk|multi[- ]omics?|omics|transcriptomics?|rna[- ]?seq|long[- ]read sequencing)\b", re.I)
_EPIDEMIOLOGY_HEALTH_DATA = re.compile(
    r"\b(?:epidemiolog(?:y|ical)|health data science|population health|longitudinal health data|electronic health records?|frailty|healthy ageing)\b",
    re.I,
)
_HUMAN_TRIAL = re.compile(
    r"\b(?:randomi[sz]ed controlled trial|cluster randomi[sz]ed|clinical trial|trial manager|intervention study|intervention research)\b",
    re.I,
)
_HUMAN_HEALTH_CONTEXT = re.compile(
    r"\b(?:young adults?|patient outcomes?|psychosocial|health psychology|behavio[u]?ral trial|self-management|rehabilitation|quality of life|health intervention)\b",
    re.I,
)
_INTEGRATIVE_BRAIN_BODY = re.compile(
    r"\b(?:microbiome|host[- ]microbe|gut[- ]brain|brain[- ]body|systems physiology|endocrine|psychosocial stress|brain function|behavio[u]?r)\b",
    re.I,
)
_EXPERIMENTAL_SPECIALIST_HARD = re.compile(
    r"\b(?:must|required|essential|mandatory|proven experience|hands[- ]on experience|expertise in)\b.{0,120}"
    r"\b(?:patch clamp|optogenetics|electrophysiology|cell culture|transplantation|single[- ]cell|flow cytometry|mass spectrometry)\b",
    re.I | re.S,
)
_SPECIALIZED_COMPUTATIONAL_COGNITION = re.compile(
    r"\b(?:bayesian cognitive model|advanced computational modelling|computational model(?:s|ling)? of (?:infant|cognit)|model-based approach)\b",
    re.I,
)
_REQUIRED_MISMATCH_PHD = re.compile(
    r"\b(?:hold|have|completed|require(?:d)?|seeking).{0,80}\bphd\b.{0,160}"
    r"\b(?:organizational psychology|organisational psychology|work and organizational psychology|work & organizational psychology|"
    r"social psychology|management|marketing|business|law|engineering|chemistry|physics)\b",
    re.I | re.S,
)
_HIGH_ALTITUDE_SPECIALTY = re.compile(r"\b(?:high[- ]altitude physiology|environmental physiology)\b", re.I)
_MRI_EXPERTISE = re.compile(r"\b(?:expertise|experience)\b.{0,100}\b(?:magnetic resonance imaging|mri)\b", re.I | re.S)


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
    evidence["e06"] = _append(list(evidence.get("e06") or []), reason)
    out["evidence"] = evidence
    return out


def _review(result: dict[str, Any], code: str, reason: str, *, remove_blockers: set[str] | None = None) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["recommendation"] = "REVIEW"
    out["pre_evaluation_disposition"] = "POLICY_REVIEW"
    if remove_blockers:
        out["blocker_codes"] = [b for b in list(out.get("blocker_codes") or []) if b not in remove_blockers]
    out["review_codes"] = _append(list(out.get("review_codes") or []), code)
    out["reason"] = reason + " " + str(out.get("reason") or "")
    evidence = copy.deepcopy(out.get("evidence") or {})
    evidence["e06"] = _append(list(evidence.get("e06") or []), reason)
    out["evidence"] = evidence
    return out


def _has_hard_policy_blocker(result: dict[str, Any]) -> bool:
    codes = set(result.get("blocker_codes") or [])
    if codes & _HARD_POLICY_CODES:
        return True
    return any(any(code.startswith(prefix) for prefix in _HARD_CODE_PREFIXES) for code in codes)


def _mandatory_german(text: str) -> bool:
    # Language evidence must be local to the same sentence/bullet. A separate
    # "German desirable" sentence must not become mandatory because another
    # requirement elsewhere contains the word "required".
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
        if not _GERMAN.search(sentence):
            continue
        if _PREFERENCE_CUE.search(sentence):
            continue
        if _GERMAN_LEVEL_OR_MANDATE.search(sentence):
            return True
    return False


def _omics_only_optional(text: str) -> bool:
    hits = list(_OMICS.finditer(text))
    if not hits:
        return False
    for hit in hits:
        start = max(0, hit.start() - 220)
        end = min(len(text), hit.end() + 220)
        window = text[start:end]
        if not _PREFERENCE_CUE.search(window):
            # Project-description mentions of genomics are not requirements.
            requirementish = re.search(r"\b(?:you will|you must|required|essential|expertise|experience|skills?|qualification)\b", window, re.I)
            if requirementish:
                return False
    return True


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluate_e05(job))
    result["evaluator_version"] = EVALUATOR_VERSION
    result["base_calibrated_evaluator_version"] = "E0.5_GENERALIZATION_CANDIDATE"

    title = _title(job)
    text = _jd(job)
    combined = f"{title} {text}"
    blockers = set(result.get("blocker_codes") or [])
    country = str((job.get("location") or {}).get("country_code") or "").upper()

    # Detect explicit policy evidence independently of inherited blocker codes.
    # This prevents a direct scientific hit from erasing an otherwise decisive
    # mobility or language restriction in lower-layer recommendation rewriting.
    if country == "AU" and _AU_NO_SPONSORSHIP.search(text) and _AU_WORK_RIGHTS_REQUIRED.search(text):
        return _skip(
            result,
            "AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED_E06",
            "The Australian posting explicitly states that sponsorship is unavailable and existing unrestricted/full work rights are required.",
        )
    if _mandatory_german(text):
        return _skip(
            result,
            "MANDATORY_GERMAN_E06",
            "German is explicitly mandatory or required at C1/C2 level; the declared profile does not establish that local-language evidence.",
        )

    # Career stage and explicit title discipline outrank incidental health/science terms.
    if _SENIOR_OUT_OF_STAGE.search(title):
        return _skip(result, "SENIOR_OUT_OF_TARGET_STAGE_E06", "The appointment is explicitly senior to the configured target career stage.")
    if _CLEAR_TITLE_DOMAIN_MISMATCH.search(title):
        return _skip(result, "EXPLICIT_TITLE_DOMAIN_MISMATCH_E06", "The vacancy title itself establishes a discipline outside the declared scientific tracks.")

    # Explicit hard policy blockers must not be softened simply because a direct scientific
    # anchor or non-English sport-science term is also present.
    if _has_hard_policy_blocker(result):
        return _skip(result, "PRESERVE_EXPLICIT_HARD_BLOCKER_E06", "A separately evidenced hard policy blocker remains decisive despite scientific-topic overlap.")

    if _REQUIRED_MISMATCH_PHD.search(text):
        return _skip(result, "MANDATORY_PHD_DISCIPLINE_MISMATCH_E06", "The required doctoral discipline establishes a specialist academic identity outside the declared profile.")

    if _SPECIALIZED_COMPUTATIONAL_COGNITION.search(combined) and re.search(
        r"\b(?:experience|expertise|strong background)\b.{0,120}\b(?:computational modelling|bayesian|machine learning|ai)\b",
        text,
        re.I | re.S,
    ):
        return _skip(result, "CENTRAL_COMPUTATIONAL_COGNITION_MISMATCH_E06", "The role is centred on specialist computational cognitive modelling rather than the candidate's established experimental/intervention profile.")

    # E0.5 could misclassify optional genomic exposure as a mandatory omics identity.
    if "MANDATORY_SPECIALIST_OMICS_GENOMICS_E05" in blockers and _EPIDEMIOLOGY_HEALTH_DATA.search(text) and _omics_only_optional(text):
        return _review(
            result,
            "EPIDEMIOLOGY_OPTIONAL_GENOMICS_REVIEW_E06",
            "The central role is epidemiology/longitudinal health-data research and genomic experience is optional rather than a mandatory specialist identity.",
            remove_blockers={"MANDATORY_SPECIALIST_OMICS_GENOMICS_E05"},
        )

    # Human intervention trials are a declared capability. Disease-specific scope can still
    # make the fit adjacent, so surface rather than auto-apply.
    if result.get("recommendation") == "SKIP" and _TARGET_POSTDOC_RESEARCH.search(title) and _HUMAN_TRIAL.search(text) and _HUMAN_HEALTH_CONTEXT.search(text):
        soft = {"NO_PROFILE_ANCHOR_IN_FULL_JD_E021", "NO_PROFILE_RELEVANCE_EVIDENCE_E04", "INSUFFICIENT_RELEVANCE_EVIDENCE_E04"}
        if blockers.issubset(soft):
            return _review(
                result,
                "HUMAN_INTERVENTION_TRIAL_REVIEW_E06",
                "A human randomized/intervention trial with psychosocial or health-outcome content is credibly adjacent to the declared RCT and intervention experience.",
                remove_blockers=soft,
            )

    # Integrative microbiome/brain-body systems can be adjacent when the posting is broad and
    # no specific wet-lab technique is explicitly mandatory.
    if result.get("recommendation") == "SKIP" and "SPECIALIST_BIOLOGY_TITLE_E021" in blockers:
        if len(_INTEGRATIVE_BRAIN_BODY.findall(text)) >= 3 and not _EXPERIMENTAL_SPECIALIST_HARD.search(text):
            return _review(
                result,
                "INTEGRATIVE_BRAIN_BODY_REVIEW_E06",
                "The integrative biology role contains multiple brain-body, stress/endocrine or microbiome anchors and no single specialist wet-lab technique is explicitly mandatory.",
                remove_blockers={"SPECIALIST_BIOLOGY_TITLE_E021", "INHERITED_EXPLICIT_HARD_E042"},
            )

    # Direct exercise science should not automatically become STRONG_APPLY when the advert
    # requires a niche expertise not established in the profile.
    if result.get("recommendation") == "STRONG_APPLY" and _HIGH_ALTITUDE_SPECIALTY.search(text) and _MRI_EXPERTISE.search(text):
        return _review(
            result,
            "DIRECT_CORE_NICHE_EXPERTISE_REVIEW_E06",
            "The scientific domain is directly relevant, but the advert explicitly asks for niche high-altitude/environmental physiology plus MRI expertise that requires human fit review.",
        )

    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
