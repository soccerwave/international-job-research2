from __future__ import annotations

import copy
import re
from typing import Any

from src.evaluation.calibrated_e04 import ADJACENT_SCIENCE, DIRECT_CORE, _jd, _title
from src.evaluation.calibrated_e042 import evaluate_calibrated as evaluate_e042

EVALUATOR_VERSION = "E0.5_GENERALIZATION_CANDIDATE"

_TARGET_RESEARCH_ROLE = re.compile(
    r"\b(?:post\s*-?\s*doc(?:toral)?|postdoctoral|post-doctoral|research fellow|research associate|"
    r"research scientist|assistant professor|lecturer|teaching fellow|tenure[- ]track|junior professor|"
    r"juniorprofessor|universit[aä]tsassistent.{0,18}postdoc|university assistant.{0,18}postdoc)\b",
    re.I,
)
_SECONDARY_ROLE_TITLE = re.compile(
    r"\b(?:grant manager|research funding manager|scientific project manager|research project manager|"
    r"research programme manager|research program manager|grants? officer|research development manager)\b",
    re.I,
)
_INVALID_VACANCY_SHELL = re.compile(
    r"^\s*(?:find jobs(?: and opportunities)?|search jobs?|job search|find opportunities|"
    r"jobs and opportunities|vacancies|career opportunities)\s*$",
    re.I,
)
_TEACHING_FELLOW = re.compile(r"\bteaching fellow\b", re.I)
_TEACHING_RELEVANT_CONTEXT = re.compile(
    r"\b(?:school|department|institute|faculty|centre|center) of (?:psychology|sport|sports|"
    r"exercise|kinesiology|health|neuroscience|movement|rehabilitation)\b|"
    r"\b(?:psychology|sport science|sports science|exercise science|exercise physiology|neuroscience|"
    r"kinesiology|rehabilitation)\b",
    re.I,
)

# _jd/_title normalize accents. These are high-specificity scientific aliases, not
# generic translations such as 'training' or 'health'.
_MULTILINGUAL_DIRECT_TERMS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\bsportwissenschaft(?:en)?\b", r"\bsport[- ]?und bewegungswissenschaft(?:en)?\b",
        r"\bsportmedizin\b", r"\bleistungsphysiologie\b", r"\btrainingswissenschaft(?:en)?\b",
        r"\bbewegungswissenschaft(?:en)?\b",
        r"\bbewegingswetenschappen\b", r"\binspanningsfysiologie\b", r"\bsportwetenschappen\b",
        r"\blichamelijke activiteit\b", r"\bsportgeneeskunde\b",
        r"\bsciences? du sport\b", r"\bphysiologie de l[' ]exercice\b", r"\bactivite physique\b",
        r"\bmedecine du sport\b",
        r"\bciencias? del deporte\b", r"\bfisiologia del ejercicio\b", r"\bactividad fisica\b",
        r"\bmedicina deportiva\b",
        r"\bscienze motorie\b", r"\bfisiologia dell[' ]esercizio\b", r"\battivita fisica\b",
        r"\bmedicina dello sport\b",
        r"\bciencias? do desporto\b", r"\bfisiologia do exercicio\b", r"\batividade fisica\b",
        r"\bmedicina desportiva\b",
    )
)

_PREFERENCE = re.compile(
    r"\b(?:preferred|preferably|desirable|desired|advantage(?:ous)?|would be an asset|is a plus|"
    r"preference (?:will|would|is|may) be given|priority (?:will|would|is|may) be given)\b",
    re.I,
)
_MANDATORY = re.compile(
    r"\b(?:required|essential|mandatory|must|you will (?:have|hold|possess)|you should (?:have|possess)|"
    r"will possess|should possess|proven experience|demonstrated experience|evidenced experience|"
    r"hands[- ]on experience|expertise in|experience in|high[- ]level analytical capability|"
    r"fluency in|expected to (?:integrate|perform|develop|design|implement|lead))\b",
    re.I,
)
_SPECIALIST_FAMILIES: dict[str, re.Pattern[str]] = {
    "ADVANCED_AI_INFORMATICS": re.compile(
        r"\b(?:large language models?|llms?|fundamental ai|machine learning|reinforcement learning|"
        r"natural language processing|nlp|novel model architectures?|scalable training algorithms?|"
        r"multi[- ]gpu|distributed[- ]computing|foundation models?|deep learning)\b", re.I),
    "STEM_CELL_TRANSPLANTATION": re.compile(
        r"\b(?:stem cell(?: culture| biology|[- ]based)?|cell transplantation|transplantation techniques?|"
        r"enteric nervous system models?|hirschsprung)\b", re.I),
    "ADVANCED_NEUROMODULATION_EPHYS": re.compile(
        r"\b(?:electrophysiolog(?:y|ical)|electromyograph(?:y|ic)|emg|transcranial magnetic stimulation|"
        r"tms|functional electrical stimulation|fes|neuromodulation)\b", re.I),
    "OMICS_GENOMICS": re.compile(
        r"\b(?:multi[- ]omics?|omics datasets?|genomics?|pangenomics?|long[- ]read sequencing|"
        r"transcriptomics?|rna[- ]?seq|whole[- ]genome|genomic variation)\b", re.I),
}
_AI_INFORMATICS_CONTEXT = re.compile(
    r"\b(?:school of informatics|department of computer science|computer science|artificial intelligence|"
    r"ai research lab|machine learning)\b", re.I)

_SOFT_RELEVANCE_BLOCKERS = {
    "NO_PROFILE_RELEVANCE_EVIDENCE_E04",
    "INSUFFICIENT_RELEVANCE_EVIDENCE_E04",
    "NO_PROFILE_ANCHOR_IN_FULL_JD_E021",
    "BOILERPLATE_ONLY_RELEVANCE_E041",
}
_SURFACED = {"STRONG_APPLY", "APPLY", "REVIEW"}
_REVIEWABLE_SCIENCE = {"ADJACENT", "GOOD", "STRONG"}


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
    evidence["e05"] = _append(list(evidence.get("e05") or []), reason)
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
    evidence["e05"] = _append(list(evidence.get("e05") or []), reason)
    out["evidence"] = evidence
    return out


def _strong_apply(result: dict[str, Any], reason: str) -> dict[str, Any]:
    out = copy.deepcopy(result)
    out["recommendation"] = "STRONG_APPLY"
    out["pre_evaluation_disposition"] = "ELIGIBLE"
    out["blocker_codes"] = [b for b in list(out.get("blocker_codes") or []) if b not in _SOFT_RELEVANCE_BLOCKERS]
    out["review_codes"] = [r for r in list(out.get("review_codes") or []) if r not in {
        "ADJACENT_SCIENTIFIC_FIT_E04", "DIRECT_FIT_REQUIRES_REVIEW_E04"
    }]
    dims = copy.deepcopy(out.get("dimensions") or {})
    dims["scientific"] = "STRONG"
    out["dimensions"] = dims
    out["reason"] = reason + " " + str(out.get("reason") or "")
    evidence = copy.deepcopy(out.get("evidence") or {})
    evidence["e05"] = _append(list(evidence.get("e05") or []), reason)
    out["evidence"] = evidence
    return out


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?;])\s+|\n+", text) if x.strip()]


def _multilingual_direct_hits(text: str) -> int:
    return sum(1 for pattern in _MULTILINGUAL_DIRECT_TERMS if pattern.search(text))


def _mandatory_specialist_family(text: str) -> str | None:
    # Sentence-local evidence prevents a preferred capability in one bullet from being
    # combined with a mandatory cue in another bullet. Preference language wins locally.
    for sentence in _sentences(text):
        if _PREFERENCE.search(sentence):
            continue
        if not _MANDATORY.search(sentence):
            continue
        for code, pattern in _SPECIALIST_FAMILIES.items():
            if pattern.search(sentence):
                return code
    return None


def _central_ai_informatics(text: str) -> bool:
    if not _AI_INFORMATICS_CONTEXT.search(text):
        return False
    hits = len(set(m.group(0).lower() for m in _SPECIALIST_FAMILIES["ADVANCED_AI_INFORMATICS"].finditer(text)))
    return hits >= 2


def evaluate_calibrated(job: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluate_e042(job))
    result["evaluator_version"] = EVALUATOR_VERSION
    result["base_calibrated_evaluator_version"] = "E0.4.2_EVIDENCE_GATED_CANDIDATE"

    title = _title(job)
    text = _jd(job)
    combined = f"{title} {text}"
    dims = result.get("dimensions") if isinstance(result.get("dimensions"), dict) else {}
    base_role_family = str(result.get("role_family") or (job.get("position") or {}).get("role_family") or "").upper()
    base_role_policy = str(result.get("role_policy_status") or "").upper()
    base_recommendation = str(result.get("recommendation") or "").upper()
    base_scientific = str(dims.get("scientific") or "").upper()

    if _INVALID_VACANCY_SHELL.fullmatch(title):
        return _skip(result, "INVALID_VACANCY_SHELL_E05", "The captured page title is a search/navigation shell rather than a vacancy identity.")

    target_role = bool(_TARGET_RESEARCH_ROLE.search(title))
    secondary_role = bool(_SECONDARY_ROLE_TITLE.search(title))
    conditional_research_role = (
        base_role_family == "OTHER_RESEARCH"
        and base_role_policy == "CONDITIONAL"
        and base_recommendation in _SURFACED
        and base_scientific in _REVIEWABLE_SCIENCE
    )
    if not target_role and not secondary_role and not conditional_research_role:
        return _skip(result, "NON_TARGET_ROLE_IDENTITY_E05", "The vacancy title does not identify a configured academic research/faculty or research-management role, and the lower evaluator has not established a reviewable conditional research role; incidental research language cannot create fit.")

    if _TEACHING_FELLOW.search(title):
        if DIRECT_CORE.search(combined) or ADJACENT_SCIENCE.search(combined) or _TEACHING_RELEVANT_CONTEXT.search(text):
            return _review(result, "RELEVANT_TEACHING_FELLOW_E05", "The teaching-only academic appointment sits in a profile-relevant or adjacent discipline, but teaching scope and subject fit require human review.", scientific="ADJACENT")
        return _skip(result, "UNRELATED_TEACHING_FELLOW_E05", "The teaching-only academic appointment has no reliable profile-relevant discipline context.")

    specialist = _mandatory_specialist_family(text)
    if specialist:
        return _skip(result, f"MANDATORY_SPECIALIST_{specialist}_E05", "The vacancy explicitly requires a specialist capability/identity that is not established in the declared profile; topic adjacency cannot override a mandatory methods mismatch.")

    if _central_ai_informatics(text):
        return _skip(result, "CENTRAL_AI_INFORMATICS_IDENTITY_E05", "The substantive vacancy identity is advanced AI/informatics, evidenced by its disciplinary context and multiple central AI/model-development requirements.")

    multilingual_hits = _multilingual_direct_hits(combined)
    if multilingual_hits >= 2:
        blockers = [b for b in list(result.get("blocker_codes") or []) if b not in _SOFT_RELEVANCE_BLOCKERS]
        if blockers:
            return _review(result, "MULTILINGUAL_DIRECT_WITH_BLOCKER_E05", "Multiple non-English direct-core scientific anchors are present, but a separate material blocker remains and needs human review.", scientific="GOOD")
        if re.search(r"\b(?:post\s*-?\s*doc(?:toral)?|postdoctoral|post-doctoral|universit[aä]tsassistent.{0,18}postdoc|university assistant.{0,18}postdoc)\b", title, re.I):
            return _strong_apply(result, "Multiple unambiguous non-English direct-core anchors establish a strong postdoctoral scientific match without a separate hard blocker.")
        return _review(result, "MULTILINGUAL_DIRECT_FIT_E05", "Multiple unambiguous non-English direct-core anchors establish scientific fit, while appointment-level fit still requires human review.", scientific="GOOD")

    return result


def with_calibrated_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(job)
    clone.setdefault("raw_extra", {})["evaluation"] = evaluate_calibrated(job)
    return clone
