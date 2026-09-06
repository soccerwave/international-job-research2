from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

STATE_VERSION = "STATE_SCHEMA_V1.0.0"
WRITER_ROLE = "CENTRAL_FINALIZER"
GOOD_DETAIL = {"FULL", "PARTIAL"}
OPEN_SOURCE_STATUSES = {"OPEN"}
CLOSED_SOURCE_STATUSES = {"CLOSED"}


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _safe_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.lower().rstrip("/")
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = f"{host}:{port}" if port else host
    path = re.sub(r"/{2,}", "/", parts.path or "/").rstrip("/") or "/"
    fragment = ""
    raw_fragment = parts.fragment or ""
    for pattern in (
        r"(?:^|/)job/(\d+)(?:$|[/?])",
        r"(?:^|/)jobs/(\d+)(?:$|[/?])",
        r"(?:^|/)ver-oferta/(\d+)(?:$|[/?])",
    ):
        match = re.search(pattern, raw_fragment, re.I)
        if match:
            fragment = f"/{match.group(0).strip('/')}"
            break
    return urlunsplit((scheme, netloc, path + fragment, "", "")).rstrip("/")


def _is_generic_listing_url(url: str) -> bool:
    if not url:
        return False
    try:
        path = urlsplit(url).path.lower().rstrip("/")
    except ValueError:
        path = url.lower().rstrip("/")
    generic_endings = (
        "/jobs", "/job", "/careers", "/career", "/vacancies", "/vacancy",
        "/job-openings", "/job-opportunities", "/employment", "/opportunities",
    )
    return path in {"", "/"} or path.endswith(generic_endings)


def _state_id(alias: str) -> str:
    return "job_" + hashlib.sha1(alias.encode("utf-8")).hexdigest()[:20]


def _aliases(record: dict[str, Any]) -> list[tuple[int, str]]:
    """Return conservative durable aliases ordered strongest to weakest.

    Generic careers/listing URLs are never identity aliases. Every canonical Stage 3
    record has a source-local source_job_id, so pairing a generic listing URL with title
    only adds false-merge risk. Cross-source fuzzy matching belongs in canonicalization,
    not durable state.
    """
    aliases: list[tuple[int, str]] = []
    canonical_id = str(record.get("canonical_id") or "").strip()
    if canonical_id:
        aliases.append((0, f"canonical:{canonical_id.lower()}"))

    source = record.get("source") or {}
    source_key = _norm(source.get("source_key")).replace(" ", "_")
    source_job_id = str(source.get("source_job_id") or "").strip()
    if source_key and source_job_id:
        aliases.append((1, f"source_id:{source_key}:{source_job_id.lower()}"))

    for value in (source.get("detail_url"), source.get("apply_url"), source.get("listing_url")):
        url = _safe_url(value)
        if url and not _is_generic_listing_url(url):
            aliases.append((2, f"url:{url}"))

    source_record_id = str(record.get("source_record_id") or "").strip()
    if source_key and source_record_id:
        aliases.append((3, f"source_record:{source_key}:{source_record_id.lower()}"))

    seen: set[str] = set()
    out: list[tuple[int, str]] = []
    for rank, alias in sorted(aliases, key=lambda item: item[0]):
        if alias and alias not in seen:
            seen.add(alias)
            out.append((rank, alias))
    return out


def _detail_simhash(detail: str) -> str:
    tokens = _norm(detail).split()
    if len(tokens) < 25:
        return ""
    shingles = [" ".join(tokens[i:i + 3]) for i in range(len(tokens) - 2)]
    vector = [0] * 64
    for shingle in shingles:
        value = int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big")
        for bit in range(64):
            vector[bit] += 1 if (value >> bit) & 1 else -1
    result = 0
    for bit, score in enumerate(vector):
        if score >= 0:
            result |= 1 << bit
    return f"{result:016x}"


def _simhash_distance(a: str, b: str) -> int:
    if not a or not b:
        return 0
    return (int(a, 16) ^ int(b, 16)).bit_count()


def _detail_resolved(snapshot: dict[str, Any]) -> bool:
    return snapshot.get("detail_status") in GOOD_DETAIL and int(snapshot.get("detail_words") or 0) > 0


def _evaluation_summary(record: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    raw_extra = record.get("raw_extra") or {}
    evaluation = record.get("evaluation") or raw_extra.get("evaluation") or {}
    if not isinstance(evaluation, dict):
        return "", {}
    recommendation = str(evaluation.get("recommendation") or "").strip().upper()
    dimensions = evaluation.get("dimensions") if isinstance(evaluation.get("dimensions"), dict) else {}
    return recommendation, dimensions


def _lifecycle(record: dict[str, Any]) -> str:
    status = str((record.get("source") or {}).get("source_status") or "UNKNOWN").upper()
    if status in OPEN_SOURCE_STATUSES:
        return "OPEN"
    if status in CLOSED_SOURCE_STATUSES:
        return "CLOSED"
    return "UNKNOWN"


def _snapshot(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source") or {}
    position = record.get("position") or {}
    location = record.get("location") or {}
    dates = record.get("dates") or {}
    contract = record.get("contract") or {}
    description = record.get("description") or {}
    detail_status = str(description.get("detail_status") or "NOT_ATTEMPTED").upper()
    detail = str(description.get("full_jd") or "") if detail_status in GOOD_DETAIL else ""
    recommendation, dimensions = _evaluation_summary(record)
    return {
        "title": _norm(position.get("title_raw") or position.get("title_normalized")),
        "institution": _norm(position.get("institution_raw") or position.get("institution_normalized")),
        "department": _norm(position.get("department")),
        "country_code": str(location.get("country_code") or "").upper(),
        "city": _norm(location.get("city")),
        "role_family": str(position.get("role_family") or "UNKNOWN").upper(),
        "role_level": str(position.get("role_level") or "UNKNOWN").upper(),
        "employment_type": str(position.get("employment_type") or "UNKNOWN").upper(),
        "workplace_mode": str(position.get("workplace_mode") or "UNKNOWN").upper(),
        "deadline_at": str(dates.get("deadline_at") or ""),
        "deadline_status": str(dates.get("deadline_status") or "UNKNOWN").upper(),
        "contract_term": str(contract.get("term_type") or "UNKNOWN").upper(),
        "duration_months": contract.get("duration_months"),
        "fte": contract.get("fte"),
        "source_status": str(source.get("source_status") or "UNKNOWN").upper(),
        "lifecycle_status": _lifecycle(record),
        "detail_status": detail_status,
        "detail_simhash": _detail_simhash(detail),
        "detail_words": len(_norm(detail).split()) if detail else 0,
        "recommendation": recommendation,
        "evaluation_dimensions": dimensions,
    }


def _quality_events(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    old_ok = _detail_resolved(previous)
    new_ok = _detail_resolved(current)
    if not old_ok and new_ok:
        return ["DETAIL_RESOLVED"]
    if old_ok and not new_ok:
        return ["DETAIL_UNRESOLVED"]
    return []


def _change_reasons(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    detail_degraded = _detail_resolved(previous) and not _detail_resolved(current)
    stable_fields = ["title", "institution", "department", "country_code", "city", "role_family", "role_level"]
    enriched_fields = [
        "employment_type", "workplace_mode", "deadline_at", "deadline_status",
        "contract_term", "duration_months", "fte", "lifecycle_status",
    ]
    fields = stable_fields if detail_degraded else stable_fields + enriched_fields
    for field in fields:
        old = previous.get(field)
        new = current.get(field)
        if old != new and (old not in {None, ""} or new not in {None, ""}):
            reasons.append(field)

    if _detail_resolved(previous) and _detail_resolved(current):
        old_hash = str(previous.get("detail_simhash") or "")
        new_hash = str(current.get("detail_simhash") or "")
        if old_hash and new_hash and _simhash_distance(old_hash, new_hash) >= 14:
            reasons.append("full_jd")
        old_rec = str(previous.get("recommendation") or "")
        new_rec = str(current.get("recommendation") or "")
        if old_rec and new_rec and old_rec != new_rec:
            reasons.append("recommendation")
    return reasons


def _snapshot_for_storage(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Keep the last trustworthy enriched values through a transient detail failure."""
    if not previous or _detail_resolved(current) or not _detail_resolved(previous):
        return current
    merged = dict(current)
    for field in (
        "employment_type", "workplace_mode", "deadline_at", "deadline_status", "contract_term",
        "duration_months", "fte", "detail_status", "detail_simhash", "detail_words",
        "recommendation", "evaluation_dimensions",
    ):
        merged[field] = previous.get(field)
    for field in ("title", "institution", "department", "country_code", "city", "role_family", "role_level"):
        if merged.get(field) in {None, ""} and previous.get(field) not in {None, ""}:
            merged[field] = previous.get(field)
    # Lifecycle is deliberately not preserved: explicit CLOSED/OPEN source evidence is
    # meaningful independently of a transient Full-JD resolution failure.
    return merged


def empty_state() -> dict[str, Any]:
    return {
        "state_version": STATE_VERSION,
        "generation": 0,
        "updated_at": None,
        "last_run_id": None,
        "writer_role": WRITER_ROLE,
        "jobs": {},
    }


def validate_state(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
        raise RuntimeError("State document has invalid top-level structure")
    if data.get("state_version") != STATE_VERSION:
        raise RuntimeError(f"Unsupported state version {data.get('state_version')!r}; expected {STATE_VERSION!r}")
    if data.get("writer_role") != WRITER_ROLE:
        raise RuntimeError("State writer_role is not CENTRAL_FINALIZER")
    generation = data.get("generation")
    if not isinstance(generation, int) or generation < 0:
        raise RuntimeError("State generation must be a non-negative integer")
    for state_id, entry in data["jobs"].items():
        if not isinstance(entry, dict) or entry.get("state_id") != state_id:
            raise RuntimeError(f"Invalid state entry {state_id!r}")
        if not isinstance(entry.get("aliases"), list) or not entry["aliases"]:
            raise RuntimeError(f"State entry {state_id!r} has no aliases")
    return data


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"State file is unreadable/corrupt: {path}: {exc}") from exc
    return validate_state(data)


def save_state_atomic(path: Path, state: dict[str, Any]) -> None:
    validate_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    temp.write_text(payload, encoding="utf-8")
    os.replace(temp, path)


def state_bytes(state: dict[str, Any]) -> bytes:
    validate_state(state)
    return (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def state_sha256(state: dict[str, Any]) -> str:
    return hashlib.sha256(state_bytes(state)).hexdigest()


def _alias_index(jobs: dict[str, dict[str, Any]]) -> dict[str, str | None]:
    index: dict[str, str | None] = {}
    for state_id, entry in jobs.items():
        for alias in entry.get("aliases") or []:
            if alias in index and index[alias] != state_id:
                index[alias] = None
            else:
                index[alias] = state_id
    return index


def apply_state(
    records: list[dict[str, Any]],
    state: dict[str, Any] | None,
    *,
    observed_at: str,
    run_id: str,
    writer_role: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply one finalizer observation set without inferring closure from absence.

    Record dictionaries are annotated under raw_extra.state. The supplied durable state
    is copied and never modified in place.
    """
    if writer_role != WRITER_ROLE:
        raise PermissionError("Durable state may only be written by CENTRAL_FINALIZER")
    if not observed_at or not run_id:
        raise ValueError("observed_at and run_id are required")

    new_state = copy.deepcopy(state if state is not None else empty_state())
    validate_state(new_state)
    jobs: dict[str, dict[str, Any]] = new_state["jobs"]
    index = _alias_index(jobs)
    counts = {"NEW": 0, "SEEN": 0, "MATERIALLY_CHANGED": 0, "REOPENED": 0}
    quality_counts = {"DETAIL_RESOLVED": 0, "DETAIL_UNRESOLVED": 0}

    for record in records:
        ranked_aliases = _aliases(record)
        aliases = [alias for _, alias in ranked_aliases]
        if not aliases:
            raise RuntimeError(f"Record {record.get('source_record_id')!r} has no durable identity alias")

        matched_ids: list[str] = []
        for _, alias in ranked_aliases:
            candidate = index.get(alias)
            if candidate and candidate not in matched_ids:
                matched_ids.append(candidate)
        if len(matched_ids) > 1:
            raise RuntimeError(
                f"State identity conflict for {record.get('source_record_id')!r}: aliases match {matched_ids}"
            )

        current = _snapshot(record)
        quality_events: list[str] = []
        change_reasons: list[str] = []

        if not matched_ids:
            seed = aliases[0]
            state_id = _state_id(seed)
            base = state_id
            suffix = 1
            while state_id in jobs:
                state_id = f"{base}_{suffix}"
                suffix += 1
            entry = {
                "state_id": state_id,
                "aliases": aliases,
                "first_seen_at": observed_at,
                "last_seen_at": observed_at,
                "times_seen": 1,
                "lifecycle_status": current["lifecycle_status"],
                "last_snapshot": current,
                "last_event": "NEW",
                "last_change_reasons": [],
            }
            jobs[state_id] = entry
            event = "NEW"
            for alias in aliases:
                if alias not in index:
                    index[alias] = state_id
        else:
            state_id = matched_ids[0]
            entry = jobs[state_id]
            previous = entry.get("last_snapshot") or {}
            quality_events = _quality_events(previous, current)
            for item in quality_events:
                quality_counts[item] += 1
            change_reasons = _change_reasons(previous, current)
            was_closed = str(entry.get("lifecycle_status") or previous.get("lifecycle_status") or "UNKNOWN") == "CLOSED"
            now_open = current.get("lifecycle_status") == "OPEN"
            if was_closed and now_open:
                event = "REOPENED"
                if "lifecycle_status" not in change_reasons:
                    change_reasons.insert(0, "lifecycle_status")
            elif change_reasons:
                event = "MATERIALLY_CHANGED"
            else:
                event = "SEEN"

            merged_aliases = list(entry.get("aliases") or [])
            for alias in aliases:
                if alias not in merged_aliases:
                    merged_aliases.append(alias)
                    if alias not in index:
                        index[alias] = state_id
            entry.update({
                "aliases": merged_aliases,
                "last_seen_at": observed_at,
                "times_seen": int(entry.get("times_seen") or 0) + 1,
                "lifecycle_status": current.get("lifecycle_status") or "UNKNOWN",
                "last_snapshot": _snapshot_for_storage(previous, current),
                "last_event": event,
                "last_change_reasons": change_reasons,
            })

        counts[event] += 1
        raw_extra = record.setdefault("raw_extra", {})
        raw_extra["state"] = {
            "state_version": STATE_VERSION,
            "state_id": state_id,
            "seen_status": event,
            "change_reasons": change_reasons,
            "quality_events": quality_events,
            "first_seen_at": jobs[state_id]["first_seen_at"],
            "last_seen_at": observed_at,
            "times_seen": jobs[state_id]["times_seen"],
            "lifecycle_status": jobs[state_id]["lifecycle_status"],
        }

    # Critical fail-open rule: entries not observed in this run remain untouched.
    new_state["generation"] = int(new_state["generation"]) + 1
    new_state["updated_at"] = observed_at
    new_state["last_run_id"] = run_id
    new_state["writer_role"] = WRITER_ROLE
    validate_state(new_state)

    summary = {
        **counts,
        **quality_counts,
        "state_version": STATE_VERSION,
        "generation": new_state["generation"],
        "state_jobs": len(jobs),
        "records_observed": len(records),
        "not_observed_inferred_closed": 0,
        "writer_role": WRITER_ROLE,
        "run_id": run_id,
        "state_sha256": state_sha256(new_state),
    }
    return new_state, summary
