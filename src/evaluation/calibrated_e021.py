from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any

from src.evaluation.calibrated_e02 import evaluate_calibrated as evaluate_e02

EVALUATOR_VERSION = "E0.2.2_CALIBRATED_SHADOW"
GOOD_DETAIL = {"FULL", "PARTIAL"}

_DIRECT_CORE = re.compile(
    r"\b(?:exercise physiology|exercise science|sport(?:s)? science|physical activity|human movement|"
    r"kinesiology|clinical exercise|exercise intervention|exercise training|aerobic exercise|"
    r"resistance training|sports medicine|psychophysiolog(?:y|ical)|psychosocial stress|"
    r"psychological stress|stress recovery|stress response|cortisol|hpa(?:-| )axis|brain health|"
    r"neurocognitive health|sportwissenschaft\w*|bewegungswissenschaft\w*|trainingswissenschaft\w*|"
    r"leistungsphysiologie|sportmedizin)\b",
    re.I,
)

_ADDITIONAL_ADJACENT_TITLE = re.compile(
    r"\b(?:brain ag(?:e)?ing|connectomics?|cortical pain circuits?|schizophrenia|nhp vision|"
    r"microbiome|microbiota|gut[- ]brain|urban health|community health|research funding manager|"
    r"grant manager|research project manager|scientific project manager|research programme manager)\b",
    re.I,
)

_ADVANCED_AI_TITLE = re.compile(r"\b(?:neuroai|machine learning|computational neuroscience)\b", re.I)
_ADVANCED_AI_BODY = re.compile(
    r"\b(?:artificial intelligence|machine learning|deep learning|self-attention|neural network|"
    r"in-context learning|computational model(?:ling|ing))\b",
    re.I,
)

_SECONDARY_PROFILE_DOMAIN = re.compile(
    r"\b(?:physiology education|physiological sciences?|human physiology|systems physiology|"
    r"cardiovascular physiology|respiratory physiology|neurophysiology)\b",
    re.I,
)
_HIGHER_ED_TEACHING = re.compile(
    r"\b(?:university|undergraduate|postgraduate|higher education|medical school)\b.{0,100}\b(?:teach|teaching|lectur(?:e|ing)|curriculum|module)\b|"
    r"\b(?:teach|teaching|lectur(?:e|ing)|curriculum|module)\b.{0,100}\b(?:university|undergraduate|postgraduate|higher education|medical school)\b",
    re.I,
)
_STUDENT_SUPERVISION = re.compile(
    r"\b(?:supervis(?:e|es|ed|ing|ion)|mentor(?:ing)?)\b.{0,100}\b(?:student|students|undergraduate|postgraduate|msc|master|doctoral|phd)\b|"
    r"\b(?:student|students|undergraduate|postgraduate|msc|master|doctoral|phd)\b.{0,100}\b(?:supervis(?:e|es|ed|ing|ion)|mentor(?:ing)?)\b",
    re.I,
)
_ACADEMIC_RESEARCH_TRACK = re.compile(
    r"\b(?:postdoctoral|post-doctoral|peer[- ]reviewed publications?|research experience|independent research|research programme|research program)\b",
    re.I,
)
_SPECIALIST_PHYSIOLOGY = re.compile(
    r"\b(?:high-altitude physiology|altitude physiology|environmental physiology|performance physiology)\b",
    re.I,
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


def _full_jd(job: dict[str, Any]) -> str:
    return _norm((job.get("description") or {}).get("full_jd") or "")


def _subject_title(title: str) -> str:
    # Some ATS titles append the organisational unit after the actual vacancy subject,
    # e.g. "Wellbeing in the Curriculum, UCD School of ... Sports Science". Scientific
    # fit must not be inferred from the school name alone.
    return re.split(
        r",\s*(?:ucd\s+)?(?:school|faculty|department|college)\s+of\b",
        title,
        maxsplit=1,
        flags=re.I,
    )[0].strip()


def _append_unique(values: list[str], value: str) -> list[str]:
    out = list(values)
    if value not in out:
        out.append(value)
    return out


def _skip(result: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
    result = copy.deepcopy(result)
    result["recommendation"] = "SKIP"
    result["pre_evaluation_disposition"] = "POLICY_SKIP"
    result["blocker_codes"] = _append_unique(list(result.get("blocker_codes") or []), code)
    evidence = copy.deepcopy(result.get("evidence") or {})
    calibration = list(evidence.get("calibration") or [])
    if reason not in calibration:
        calibration.append(reason)
    evidence["calibration"] = calibration
    result["evidence"] = evidence
    result["reason"] = reason + " " + str(result.get("reason") or "")
    return result


def _review(result: dict[str, Any], code: str, reason: str, scientific: str | None = None) -> dict[str, Any]:
    result = copy.deepcopy(result)
    result["recommendation"] = "REVIEW"
    result["pre_evaluation_disposition"] = "POLICY_REVIEW"
    result["review_codes"] = _append_unique(list(result.get("review_codes") or []), code)
    if scientific:
        dimensions = copy.deepcopy(result.get("dimensions") or {})
        dimensions["scientific"] = scientific
        result["dimensions"] = dimensions
    evidence = copy.deepcopy(result.get("evidence") or {})
    calibration = list(evidence.get("calibration") or [])
    if reason not in calibration:
        calibration.append(reason)
    evidence["calibration"] = calibration
    result["evidence"] = evidence
    result["reason"] = reason + " " + str(result.get("reason") or "")
    return result


def _strong(result: dict[str, Any], reason: str) -> dict[str, Any]:
    result = copy.deepcopy(result)
    dimensions = copy.deepcopy(result.get("dimensions") or {})
    dimensions["scientific"] = "STRONG"
    result["dimensions"] = dimensions
    if str(result.get("role_family") or "").upper() == "POSTDOC" and str(dimensions.get("level") or "").upper() == "STRONG":
        if not result.get("blocker_codes") and not result.get("review_codes"):
            result["recommendation"] = "STRONG_APPLY"
            result["pre_evaluation_disposition"] = "ELIGIBLE_FOR_EVALUATION"
    evidence = copy.deepcopy(result.get("evidence") or {})
    calibration = list(evidence.get("calibration") or [])
    if reason not in calibration:
        calibration.append(reason)
    evidence["calibration"] = calibration
    result["evidence"] = evidence
    result["reason"] = reason + " " + str(result.get("reason") or "")
    return result


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluate_e02(job))
    result["evaluator_version"] = EVALUATOR_VERSION
    result["base_calibrated_evaluator_version"] = result.get("base_evaluator_version") or "E0.2_CALIBRATED_SHADOW"

    title = _title(job)
    subject_title = _subject_title(title)
    full_jd = _full_jd(job)
    detail_status = str((job.get("description") or {}).get("detail_status") or "NOT_ATTEMPTED").upper()
    has_full_detail = detail_status in GOOD_DETAIL and len(full_jd) >= 300
    direct_subject_core = bool(_DIRECT_CORE.search(subject_title))
    direct_body_core = bool(_DIRECT_CORE.search(full_jd))

    # A job located inside a sports/public-health school is not automatically a sport-
    # science vacancy. The actual vacancy subject controls routing.
    if re.search(r"\bwell-?being in the curriculum\b|\bwellbeing in the curriculum\b", subject_title, re.I):
        return _review(
            result,
            "ADJACENT_WELLBEING_CURRICULUM_E021",
            "The role is an adjacent wellbeing/curriculum project; the organisational school name is not treated as direct exercise-science fit.",
            scientific="ADJACENT",
        )

    # Specialist physiology subdomains are adjacent unless the posting also contains
    # an independently established direct profile anchor. Do not infer capability from
    # the generic word "physiology" or from a Sport Science department name.
    if (
        _SPECIALIST_PHYSIOLOGY.search(full_jd)
        and not direct_subject_core
        and str(result.get("role_family") or "").upper() == "POSTDOC"
    ):
        result = _review(
            result,
            "SPECIALIST_PHYSIOLOGY_ADJACENT_E022",
            "The vacancy centres on a specialist physiology subdomain not independently established in the profile; retain for review rather than auto-apply.",
            scientific="ADJACENT",
        )

    # Advanced AI/ML is a declared non-established capability. When it is central in the
    # title and project rather than merely a preferred tool, it is a hard methods mismatch.
    if _ADVANCED_AI_TITLE.search(subject_title) and _ADVANCED_AI_BODY.search(full_jd) and not direct_subject_core:
        return _skip(
            result,
            "ADVANCED_AI_ML_CENTRAL_E021",
            "Advanced AI/machine-learning/computational modelling is central to the vacancy and is not established as an independent core research capability in the profile.",
        )

    # Clinical Psychology faculty posts explicitly requiring professional clinical-
    # psychology qualifications/clinical practice are not interchangeable with stress or
    # psychological-outcome research experience.
    if re.search(r"\bclinical psychology\b", subject_title, re.I) and (
        re.search(r"\bdoctorate in clinical psychology\b", full_jd, re.I)
        or re.search(r"\baccredited professional qualification in clinical psychology\b", full_jd, re.I)
        or re.search(r"\bexperience as a clinician\b", full_jd, re.I)
    ):
        return _skip(
            result,
            "CLINICAL_PSYCHOLOGY_QUALIFICATION_E021",
            "The vacancy explicitly requires clinical-psychology professional qualifications/clinical practice that are not established in the profile.",
        )

    # Explicit electrophysiology expertise is outside the declared methods profile.
    if re.search(
        r"\b(?:expertise|expert|demonstrated experience|strong experience|proven experience)\b.{0,100}\belectrophysiolog(?:y|ical)\b|"
        r"\belectrophysiolog(?:y|ical)\b.{0,100}\b(?:expertise|expert|required|essential|experience)\b",
        full_jd,
        re.I,
    ):
        return _skip(
            result,
            "MANDATORY_ELECTROPHYSIOLOGY_E021",
            "The posting explicitly requires electrophysiology expertise, a method the profile says not to infer.",
        )

    # Specialist wet-lab identity in the role title is not rescued by a broader project
    # theme such as microbiome-gut-brain or stress.
    if re.search(r"\b(?:immunologist|integrative biologist)\b", subject_title, re.I):
        return _skip(
            result,
            "SPECIALIST_BIOLOGY_TITLE_E021",
            "The post is explicitly for a specialist immunology/integrative-biology profile rather than the candidate's exercise/stress research profile.",
        )

    # Philosophy faculty is a discipline mismatch even when a module includes cognitive
    # science; cognitive adjacency alone is insufficient for an academic appointment in philosophy.
    if re.search(r"\bphilosophy\b", subject_title, re.I) and str(result.get("role_family") or "").upper() in {"LECTURER", "ASSISTANT_PROFESSOR"}:
        return _skip(
            result,
            "FACULTY_DISCIPLINE_PHILOSOPHY_E021",
            "The academic appointment is in Philosophy; cognitive-science adjacency does not establish discipline-level faculty fit.",
        )

    # Recover a small set of genuine adjacent themes that E0.2 intentionally did not
    # promote automatically. These remain REVIEW, never APPLY.
    if _ADDITIONAL_ADJACENT_TITLE.search(subject_title) and str(result.get("recommendation") or "").upper() in {"LOW_PRIORITY", "SKIP"}:
        return _review(
            result,
            "ADDITIONAL_ADJACENT_THEME_E021",
            "The title contains a genuine adjacent health/neuroscience/microbiome or research-funding theme that merits human review but not automatic apply routing.",
            scientific="ADJACENT",
        )

    # Distinguish "no relevant evidence" from "relevant evidence not represented in
    # the narrow direct-anchor vocabulary". A target-stage role with a secondary profile
    # domain plus multiple independently documented academic strengths is surfaced for
    # human review. Generic academic language alone is not enough.
    scientific = str((result.get("dimensions") or {}).get("scientific") or "UNCLEAR").upper()
    if (
        str(result.get("recommendation") or "").upper() == "LOW_PRIORITY"
        and scientific == "UNCLEAR"
        and has_full_detail
        and not direct_subject_core
        and not direct_body_core
    ):
        secondary_domain = bool(_SECONDARY_PROFILE_DOMAIN.search(f"{subject_title} {full_jd}"))
        academic_signal_count = sum(
            (
                bool(_HIGHER_ED_TEACHING.search(full_jd)),
                bool(_STUDENT_SUPERVISION.search(full_jd)),
                bool(_ACADEMIC_RESEARCH_TRACK.search(full_jd)),
            )
        )
        if secondary_domain and academic_signal_count >= 2:
            return _review(
                result,
                "SECONDARY_PROFILE_EVIDENCE_REVIEW_E022",
                "The posting contains a profile-adjacent scientific domain together with multiple documented academic strengths; lack of a narrow direct anchor is not treated as negative evidence.",
                scientific="ADJACENT",
            )
        return _skip(
            result,
            "NO_PROFILE_ANCHOR_IN_FULL_JD_E021",
            "A substantial Full JD was available but contained neither a reliable direct profile anchor nor enough secondary profile evidence to justify surfacing the vacancy.",
        )

    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
