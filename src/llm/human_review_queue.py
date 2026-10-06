from __future__ import annotations

from typing import Any, Iterable

VALID_LABELS = {
    "RULE_CORRECT",
    "LLM_CORRECT",
    "BOTH_REASONABLE",
    "BOTH_WRONG",
    "INSUFFICIENT_INFORMATION",
}

FALSE_NEGATIVE_TAGS = {
    "RULE_SKIP_LLM_STRONG_APPLY",
    "RULE_SKIP_LLM_APPLY",
    "RULE_LOW_PRIORITY_LLM_STRONG_APPLY",
    "RULE_LOW_PRIORITY_LLM_APPLY",
    "RULE_REVIEW_LLM_STRONG_APPLY",
    "RULE_REVIEW_LLM_APPLY",
}


def _priority(row: dict[str, Any]) -> int:
    tags = set(row.get("disagreement_tags") or [])
    if "RULE_SKIP_LLM_STRONG_APPLY" in tags:
        return 100
    if "RULE_SKIP_LLM_APPLY" in tags:
        return 95
    if tags & {"RULE_LOW_PRIORITY_LLM_STRONG_APPLY", "RULE_LOW_PRIORITY_LLM_APPLY"}:
        return 90
    if tags & {"RULE_REVIEW_LLM_STRONG_APPLY", "RULE_REVIEW_LLM_APPLY"}:
        return 85
    if "RULE_APPLY_LLM_SKIP" in tags:
        return 80
    if row.get("is_disagreement"):
        return 70
    return 0


def build_human_review_queue(comparisons: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in comparisons:
        job_id = str(row.get("job_id") or "").strip()
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        priority = _priority(row)
        if priority <= 0:
            continue
        tags = list(row.get("disagreement_tags") or [])
        queue.append({
            "schema_version": "LLM_HUMAN_REVIEW_QUEUE_V0.1",
            "job_id": job_id,
            "evaluation_id": row.get("evaluation_id"),
            "priority": priority,
            "false_negative_candidate": bool(set(tags) & FALSE_NEGATIVE_TAGS),
            "rule_recommendation": row.get("rule_recommendation"),
            "llm_decision": row.get("llm_decision"),
            "llm_fit_score": row.get("llm_fit_score"),
            "llm_confidence": row.get("llm_confidence"),
            "evidence_quality": row.get("evidence_quality"),
            "decision_distance": row.get("decision_distance"),
            "direction": row.get("direction"),
            "disagreement_tags": tags,
            "human_label": None,
            "human_notes": None,
        })
    queue.sort(key=lambda x: (-int(x["priority"]), -int(x.get("llm_confidence") or 0), str(x["job_id"])))
    return queue


def apply_human_label(item: dict[str, Any], label: str, notes: str | None = None) -> dict[str, Any]:
    normalized = str(label or "").strip().upper()
    if normalized not in VALID_LABELS:
        raise ValueError(f"invalid human review label: {label}")
    updated = dict(item)
    updated["human_label"] = normalized
    updated["human_notes"] = notes
    return updated
