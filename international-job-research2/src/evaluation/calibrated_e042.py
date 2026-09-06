from __future__ import annotations

import copy
import re
from typing import Any

from src.evaluation.calibrated_e04 import ADJACENT_SCIENCE, DIRECT_CORE, _jd, _title
from src.evaluation.calibrated_e041 import evaluate_calibrated as evaluate_e041

EVALUATOR_VERSION = "E0.4.2_EVIDENCE_GATED_CANDIDATE"

_INHERITED_HARD = {
    "ROLE_STUDENT_E02",
    "ROLE_SUPPORT_OR_ASSISTANT_E02",
    "HIGH_CONFIDENCE_UNRELATED_TITLE_E02",
    "CLINICAL_PSYCHOLOGY_QUALIFICATION_E021",
    "ADVANCED_AI_ML_CENTRAL_E021",
    "SPECIALIST_BIOLOGY_TITLE_E021",
    "FACULTY_DISCIPLINE_PHILOSOPHY_E021",
}

_ADJUNCT_POOL = re.compile(
    r"\badjunct (?:appointments?|clinical appointments?|professor|senior lecturer|lecturer)\b|"
    r"\bhonorary appointments?\b",
    re.I,
)

_SECONDARY_ROLE_TITLE = re.compile(
    r"\b(?:grant manager|research funding manager|scientific project manager|research project manager|"
    r"research programme manager|research program manager|grants? officer|research development manager)\b",
    re.I,
)

_CENTRAL_SPECIALIST_TITLE = {
    "BIOINFORMATICS_OMICS": re.compile(r"\b(?:bioinformatics|multi-omics|multiomics|computational genomics)\b", re.I),
    "COMPUTATIONAL_NEUROSCIENCE": re.compile(r"\bcomputational neuroscience\b", re.I),
    "NHP_EXPERIMENTAL_NEUROSCIENCE": re.compile(r"\b(?:nhp|non-human primate|nonhuman primate)\b", re.I),
    "MRNA_IMMUNOTHERAPY": re.compile(r"\b(?:mrna .*immunotherap|mrna cancer|cancer immunotherap)\b", re.I),
    "NEURODEGENERATION_MODELS": re.compile(r"\b(?:parkinson(?:'s)?|neurodegenerat(?:ion|ive))\b", re.I),
}

_ADVANCED_FMRI = re.compile(r"\badvanced (?:analysis|analyses) of f?mri\b", re.I)
_MANDATORY_CUE = re.compile(r"\b(?:required|essential|mandatory|must have|must demonstrate|must possess)\b", re.I)
_NEGATED_MANDATORY_CUE = re.compile(
    r"\b(?:not|isn't|is not|are not|need not|does not need to be)\b.{0,40}\b(?:required|essential|mandatory)\b",
    re.I,
)

_COMPUTATIONAL_CENTRAL = re.compile(
    r"\b(?:develop(?:ing)?|implement(?:ing)?) (?:and )?(?:statistical and )?computational models?\b|"
    r"\bhigh[- ]density neural recordings?\b|\bdetailed biophysical modell?ing\b|"
    r"\badvanced signal processing\b",
    re.I,
)
_BIOINFO_CENTRAL = re.compile(
    r"\b(?:bioinformatics|genomics|transcriptomics|rna-?seq|single[- ]cell|long[- ]read|"
    r"genome assembly|high-throughput sequencing|computational biology)\b",
    re.I,
)
_NHP_CENTRAL = re.compile(
    r"\b(?:non-human primates?|nonhuman primates?|nhps?|electrophysiological recording|microstimulation|"
    r"neuroprosthes(?:is|es)|implanted .*electrodes?)\b",
    re.I,
)
_MRNA_CENTRAL = re.compile(
    r"\b(?:mrna sciences?|molecular biology|immunology|cancer immunotherapy|cancer vaccines?)\b",
    re.I,
)
_NEURODEGEN_REQUIRED_IDENTITY = re.compile(
    r"\bph\.?d\.?\s+in\s+(?:neurodegenerative disorders?|neurodegeneration|parkinson(?:'s)? disease)\b.{0,180}\b(?:rodent|mouse|mice)\b|"
    r"\b(?:proven|demonstrated) experience\b.{0,160}\bneurodegenerat(?:ion|ive)\b.{0,200}\b(?:rodent|mouse|mice)\b",
    re.I,
)

_PREFERENCE = re.compile(
    r"\b(?:preferred|preferably|desirable|desired|advantage(?:ous)?|would be an asset|is a plus|"
    r"preference (?:will|would|is|may) be given|priority (?:will|would|is|may) be given)\b",
    re.I,
)
_MOLECULAR_SPECIALIST = re.compile(
    r"\b(?:molecular biology|aso biochemistry|two-photon imaging|2-photon imaging|stereotaxic(?:-guided)? injections?|"
    r"optogenetics?|patch clamp)\b",
    re.I,
)
_MOLECULAR_MANDATORY = re.compile(
    r"\b(?:molecular biology|aso biochemistry|two-photon imaging|2-photon imaging|stereotaxic(?:-guided)? injections?|"
    r"optogenetics?|patch clamp)\b.{0,160}\b(?:required|essential|mandatory|must)\b|"
    r"\b(?:required|essential|mandatory|must)\b.{0,160}\b(?:molecular biology|aso biochemistry|two-photon imaging|2-photon imaging|stereotaxic(?:-guided)? injections?|optogenetics?|patch clamp)\b",
    re.I,
)
_PREFERENCE_BLOCK = re.compile(
    r"\b(?:preference|priority) (?:will|would|is|may) be given\b.{0,900}",
    re.I,
)


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
    evidence["e042"] = _append(list(evidence.get("e042") or []), reason)
    out["evidence"] = evidence
    return out


def _review(result: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["recommendation"] = "REVIEW"
    out["pre_evaluation_disposition"] = "POLICY_REVIEW"
    out["review_codes"] = _append(list(out.get("review_codes") or []), code)
    out["reason"] = reason + " " + str(out.get("reason") or "")
    evidence = copy.deepcopy(out.get("evidence") or {})
    evidence["e042"] = _append(list(evidence.get("e042") or []), reason)
    out["evidence"] = evidence
    return out


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?;])\s+|\n+", text) if x.strip()]


def _advanced_fmri_is_mandatory(text: str) -> bool:
    for sentence in _sentences(text):
        if not _ADVANCED_FMRI.search(sentence):
            continue
        if _NEGATED_MANDATORY_CUE.search(sentence):
            continue
        if _MANDATORY_CUE.search(sentence):
            return True
    return False


def _molecular_blocker_is_preference_only(text: str) -> bool:
    preference = _PREFERENCE_BLOCK.search(text)
    if not preference or not _MOLECULAR_SPECIALIST.search(preference.group(0)):
        return False
    without_preference = text[: preference.start()] + " " + text[preference.end():]
    return not _MOLECULAR_MANDATORY.search(without_preference)


def _central_title_mismatch(title: str, text: str) -> str | None:
    if _CENTRAL_SPECIALIST_TITLE["BIOINFORMATICS_OMICS"].search(title) and _BIOINFO_CENTRAL.search(text):
        return "BIOINFORMATICS_OMICS"
    if _CENTRAL_SPECIALIST_TITLE["COMPUTATIONAL_NEUROSCIENCE"].search(title) and len(_COMPUTATIONAL_CENTRAL.findall(text)) >= 2:
        return "COMPUTATIONAL_NEUROSCIENCE"
    if _CENTRAL_SPECIALIST_TITLE["NHP_EXPERIMENTAL_NEUROSCIENCE"].search(title) and len(_NHP_CENTRAL.findall(text)) >= 2:
        return "NHP_EXPERIMENTAL_NEUROSCIENCE"
    if _CENTRAL_SPECIALIST_TITLE["MRNA_IMMUNOTHERAPY"].search(title) and len(_MRNA_CENTRAL.findall(text)) >= 2:
        return "MRNA_IMMUNOTHERAPY"
    if _CENTRAL_SPECIALIST_TITLE["NEURODEGENERATION_MODELS"].search(title) and _NEURODEGEN_REQUIRED_IDENTITY.search(text):
        return "NEURODEGENERATION_MODELS"
    return None


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluate_e041(job))
    result["evaluator_version"] = EVALUATOR_VERSION
    result["base_calibrated_evaluator_version"] = "E0.4.1_EVIDENCE_GATED_CANDIDATE"

    title = _title(job)
    text = _jd(job)
    title_direct = bool(DIRECT_CORE.search(title))
    title_adjacent = bool(ADJACENT_SCIENCE.search(title))
    blockers = set(result.get("blocker_codes") or [])

    inherited = blockers & _INHERITED_HARD
    if inherited and not title_direct:
        return _skip(
            result,
            "INHERITED_EXPLICIT_HARD_E042",
            "Explicit out-of-scope or unrelated-title evidence from the lower evaluator takes precedence over incidental relevance signals elsewhere in the page.",
        )

    if _ADJUNCT_POOL.search(title):
        return _skip(result, "ADJUNCT_HONORARY_POOL_E042", "The posting is an adjunct/honorary appointment pool rather than a target substantive vacancy.")

    if _advanced_fmri_is_mandatory(text):
        return _skip(result, "MANDATORY_ADVANCED_FMRI_ANALYSIS_E042", "Advanced independent fMRI analysis is explicitly required and is not established in the declared profile.")

    central = _central_title_mismatch(title, text)
    if central and not title_direct:
        return _skip(
            result,
            f"CENTRAL_SPECIALIST_IDENTITY_{central}_E042",
            "The vacancy title and substantive requirements jointly define a specialist research identity outside the established profile; topical neuroscience/health adjacency is insufficient.",
        )

    if "SECONDARY_TRACK_E04" in set(result.get("review_codes") or []) and not _SECONDARY_ROLE_TITLE.search(title):
        if not title_direct and not title_adjacent:
            return _skip(
                result,
                "INCIDENTAL_GRANT_LANGUAGE_NOT_SECONDARY_ROLE_E042",
                "Grant/funding duties inside a scientific vacancy do not convert the role into the configured grant/project-management secondary track.",
            )

    molecular_blockers = [b for b in blockers if b == "CENTRAL_MOLECULAR_WETLAB_E04"]
    if molecular_blockers and _molecular_blocker_is_preference_only(text):
        out = copy.deepcopy(result)
        out["blocker_codes"] = [b for b in out.get("blocker_codes") or [] if b not in molecular_blockers]
        return _review(
            out,
            "SPECIALIST_METHODS_PREFERRED_NOT_REQUIRED_E042",
            "Specialist molecular methods/background are preference-qualified rather than mandatory; the adjacent scientific role remains a human-review case instead of a hard skip.",
        )

    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
