from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
COMPARISON_SCHEMA_PATH = ROOT / "schemas" / "llm_shadow_comparison.schema.json"

RULE_RANK = {
    "SKIP": 0,
    "LOW_PRIORITY": 1,
    "REVIEW": 2,
    "APPLY": 3,
    "STRONG_APPLY": 4,
}
LLM_RANK = {
    "SKIP": 0,
    "REVIEW": 2,
    "APPLY": 3,
    "STRONG_APPLY": 4,
}


class ShadowComparisonError(RuntimeError):
    pass


def _load_schema() -> dict[str, Any]:
    return json.loads(COMPARISON_SCHEMA_PATH.read_text(encoding="utf-8"))


def _job_id(job: dict[str, Any]) -> str:
    return str(job.get("canonical_id") or job.get("source_record_id") or "").strip()


def _rule_evaluation(job: dict[str, Any]) -> dict[str, Any]:
    top = job.get("evaluation")
    if isinstance(top, dict):
        return top
    raw = job.get("raw_extra") or {}
    nested = raw.get("evaluation")
    return nested if isinstance(nested, dict) else {}


def _tags(rule: str, llm: str, distance: int) -> list[str]:
    tags: list[str] = []

    if rule == "SKIP" and llm == "STRONG_APPLY":
        tags.append("RULE_SKIP_LLM_STRONG_APPLY")
    elif rule == "SKIP" and llm == "APPLY":
        tags.append("RULE_SKIP_LLM_APPLY")

    if rule == "LOW_PRIORITY" and llm == "STRONG_APPLY":
        tags.append("RULE_LOW_PRIORITY_LLM_STRONG_APPLY")
    elif rule == "LOW_PRIORITY" and llm == "APPLY":
        tags.append("RULE_LOW_PRIORITY_LLM_APPLY")

    if rule == "REVIEW" and llm == "STRONG_APPLY":
        tags.append("RULE_REVIEW_LLM_STRONG_APPLY")
    elif rule == "REVIEW" and llm == "APPLY":
        tags.append("RULE_REVIEW_LLM_APPLY")

    if rule in {"APPLY", "STRONG_APPLY"} and llm == "SKIP":
        tags.append("RULE_APPLY_LLM_SKIP")

    if abs(distance) >= 2:
        tags.append("DECISION_DISTANCE_GE_2")

    if distance > 0:
        tags.append("LLM_UPRANK")
    elif distance < 0:
        tags.append("LLM_DOWNRANK")

    return tags


def compare_shadow_result(canonical_job: dict[str, Any], shadow_record: dict[str, Any]) -> dict[str, Any]:
    job_id = _job_id(canonical_job)
    shadow_job_id = str(shadow_record.get("job_id") or "").strip()
    if not job_id:
        raise ShadowComparisonError("canonical job has no stable identifier")
    if shadow_job_id != job_id:
        raise ShadowComparisonError(f"shadow job_id mismatch: expected {job_id}, got {shadow_job_id or '<missing>'}")

    rule_eval = _rule_evaluation(canonical_job)
    rule = str(rule_eval.get("recommendation") or "").upper()
    if rule not in RULE_RANK:
        raise ShadowComparisonError(f"unsupported or missing rule recommendation: {rule or '<missing>'}")

    llm_result = shadow_record.get("llm_result")
    if not isinstance(llm_result, dict):
        raise ShadowComparisonError("shadow record has no llm_result object")
    llm = str(llm_result.get("decision") or "").upper()
    if llm not in LLM_RANK:
        raise ShadowComparisonError(f"unsupported or missing LLM decision: {llm or '<missing>'}")

    evaluation_id = str(shadow_record.get("evaluation_id") or "").strip()
    if not evaluation_id:
        raise ShadowComparisonError("shadow record has no evaluation_id")

    distance = LLM_RANK[llm] - RULE_RANK[rule]
    direction = "AGREEMENT" if distance == 0 else ("LLM_UPRANK" if distance > 0 else "LLM_DOWNRANK")
    result = {
        "schema_version": "LLM_SHADOW_COMPARISON_V0.1",
        "job_id": job_id,
        "evaluation_id": evaluation_id,
        "rule_evaluator_version": rule_eval.get("evaluator_version"),
        "rule_recommendation": rule,
        "llm_decision": llm,
        "llm_fit_score": int(llm_result["fit_score"]),
        "llm_confidence": int(llm_result["confidence"]),
        "evidence_quality": llm_result["evidence_quality"],
        "decision_distance": distance,
        "direction": direction,
        "is_disagreement": distance != 0,
        "disagreement_tags": _tags(rule, llm, distance),
        "rule_score": None,
        "score_comparison_status": "UNAVAILABLE_NO_RULE_COMPOSITE_SCORE",
    }

    validator = Draft202012Validator(_load_schema())
    errors = sorted(validator.iter_errors(result), key=lambda error: list(error.path))
    if errors:
        raise ShadowComparisonError("invalid comparison output: " + "; ".join(error.message for error in errors))
    return result


def compare_available_shadow_results(
    canonical_jobs: Iterable[dict[str, Any]],
    shadow_records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    jobs_by_id = {_job_id(job): job for job in canonical_jobs if _job_id(job)}
    comparisons: list[dict[str, Any]] = []
    seen_shadow_job_ids: set[str] = set()

    for shadow in shadow_records:
        job_id = str(shadow.get("job_id") or "").strip()
        if not job_id:
            raise ShadowComparisonError("shadow record has no job_id")
        if job_id in seen_shadow_job_ids:
            raise ShadowComparisonError(f"duplicate shadow result for job_id: {job_id}")
        seen_shadow_job_ids.add(job_id)
        job = jobs_by_id.get(job_id)
        if job is None:
            raise ShadowComparisonError(f"no canonical job found for shadow job_id: {job_id}")
        comparisons.append(compare_shadow_result(job, shadow))

    return comparisons


def comparison_summary(comparisons: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(comparisons)
    tag_counts: Counter[str] = Counter()
    direction_counts: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()
    llm_counts: Counter[str] = Counter()

    for row in rows:
        tag_counts.update(row.get("disagreement_tags") or [])
        direction_counts[str(row["direction"])] += 1
        rule_counts[str(row["rule_recommendation"])] += 1
        llm_counts[str(row["llm_decision"])] += 1

    return {
        "compared": len(rows),
        "agreements": sum(1 for row in rows if not row["is_disagreement"]),
        "disagreements": sum(1 for row in rows if row["is_disagreement"]),
        "direction_counts": dict(sorted(direction_counts.items())),
        "tag_counts": dict(sorted(tag_counts.items())),
        "rule_recommendation_counts": dict(sorted(rule_counts.items())),
        "llm_decision_counts": dict(sorted(llm_counts.items())),
        "rule_score_comparison_available": False,
        "rule_score_comparison_status": "UNAVAILABLE_NO_RULE_COMPOSITE_SCORE",
    }
