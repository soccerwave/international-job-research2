from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from src.state.engine import _aliases, _safe_url

URL_FIELDS = ("detail_url", "apply_url", "listing_url")


def build_state_identity_projection(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create a state-only copy with repeated URL aliases suppressed.

    Stage 8 intentionally accepts several durable aliases, including vacancy URLs. In
    multi-source Stage 10 runs, board-level listing/apply URLs can legitimately be shared
    by many distinct canonical vacancies. Such repeated URLs are unsafe identity aliases
    and previously collapsed different jobs inside one state generation.

    The canonical/reporting records remain untouched. Only the copy passed to the frozen
    Stage 8 state engine has repeated URL aliases blanked. Canonical ID and source-local
    source_job_id remain available as strong durable aliases.
    """
    normalized_counts: Counter[str] = Counter()

    for record in records:
        source = record.get("source") or {}
        seen_for_record: set[str] = set()
        for field in URL_FIELDS:
            normalized = _safe_url(source.get(field))
            if normalized and normalized not in seen_for_record:
                normalized_counts[normalized] += 1
                seen_for_record.add(normalized)

    repeated = {url for url, count in normalized_counts.items() if count > 1}
    projected = copy.deepcopy(records)
    suppressed_by_field: Counter[str] = Counter()
    affected_records = 0

    for record in projected:
        source = record.get("source") or {}
        affected = False
        for field in URL_FIELDS:
            normalized = _safe_url(source.get(field))
            if normalized and normalized in repeated:
                source[field] = ""
                suppressed_by_field[field] += 1
                affected = True
        if affected:
            affected_records += 1

    alias_owner: dict[str, str] = {}
    collisions: dict[str, list[str]] = {}
    for record in projected:
        canonical_id = str(record.get("canonical_id") or "").strip()
        if not canonical_id:
            raise RuntimeError("State identity projection requires canonical_id on every record")
        for _, alias in _aliases(record):
            owner = alias_owner.get(alias)
            if owner is None:
                alias_owner[alias] = canonical_id
            elif owner != canonical_id:
                owners = collisions.setdefault(alias, [owner])
                if canonical_id not in owners:
                    owners.append(canonical_id)

    if collisions:
        sample = "; ".join(f"{alias} -> {owners[:3]}" for alias, owners in list(collisions.items())[:5])
        raise RuntimeError(f"Unsafe cross-record state identity aliases remain after projection: {sample}")

    summary = {
        "projection_version": "STAGE10_STATE_IDENTITY_PROJECTION_V1.0.0",
        "records": len(records),
        "repeated_url_alias_values": len(repeated),
        "affected_records": affected_records,
        "suppressed_url_aliases": int(sum(suppressed_by_field.values())),
        "suppressed_by_field": {field: int(suppressed_by_field.get(field, 0)) for field in URL_FIELDS},
        "remaining_cross_record_alias_collisions": 0,
        "canonical_records_mutated": False,
        "policy": "Repeated URL aliases across distinct canonical records are excluded from state identity only.",
    }
    return projected, summary


def sync_state_annotations(
    canonical_records: list[dict[str, Any]],
    projected_records: list[dict[str, Any]],
) -> None:
    """Copy Stage 8 state annotations from the projection back to canonical records."""
    by_id: dict[str, dict[str, Any]] = {}
    for record in projected_records:
        canonical_id = str(record.get("canonical_id") or "").strip()
        if not canonical_id:
            raise RuntimeError("State projection record is missing canonical_id")
        if canonical_id in by_id:
            raise RuntimeError(f"Duplicate canonical_id in state projection: {canonical_id}")
        state = copy.deepcopy((record.get("raw_extra") or {}).get("state"))
        if not isinstance(state, dict):
            raise RuntimeError(f"State annotation missing for canonical_id={canonical_id}")
        by_id[canonical_id] = state

    if len(by_id) != len(canonical_records):
        raise RuntimeError("State projection annotation count does not match canonical record count")

    state_ids: set[str] = set()
    for record in canonical_records:
        canonical_id = str(record.get("canonical_id") or "").strip()
        if canonical_id not in by_id:
            raise RuntimeError(f"No state annotation for canonical_id={canonical_id}")
        state = by_id[canonical_id]
        state_id = str(state.get("state_id") or "").strip()
        if not state_id:
            raise RuntimeError(f"State annotation missing state_id for canonical_id={canonical_id}")
        if state_id in state_ids:
            raise RuntimeError(f"Two canonical records resolved to the same state_id: {state_id}")
        state_ids.add(state_id)
        record.setdefault("raw_extra", {})["state"] = state
