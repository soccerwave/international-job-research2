from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from src.state.engine import WRITER_ROLE, state_sha256, validate_state
from src.state.r2_store import R2StateStore

ALLOWED_BACKUP_PREFIXES = ("state/backups/", "state/bootstrap/")
PRODUCTION_STATE_KEY = "state/current/state.json"


def _body_bytes(body: Any) -> bytes:
    value = body.read() if hasattr(body, "read") else body
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    raise RuntimeError("R2 backup returned an unsupported body type")


def _assert_production_store(store: R2StateStore) -> None:
    if str(getattr(store, "prefix", "") or "").strip("/") or store.current_key != PRODUCTION_STATE_KEY:
        raise RuntimeError("Recovery is restricted to the unprefixed authoritative production state")


def _validate_backup_key(key: str) -> str:
    clean = str(key or "").strip("/")
    if not clean.startswith(ALLOWED_BACKUP_PREFIXES):
        raise ValueError("Recovery key must be under state/backups/ or state/bootstrap/")
    if clean == PRODUCTION_STATE_KEY:
        raise ValueError("Recovery source may not be the authoritative current object")
    return clean


def load_backup_state(store: R2StateStore, backup_key: str) -> dict[str, Any]:
    _assert_production_store(store)
    key = _validate_backup_key(backup_key)
    response = store.client.get_object(Bucket=store.bucket, Key=key)
    raw = _body_bytes(response.get("Body"))
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Recovery backup is corrupt JSON: {key}") from exc
    validate_state(state)
    metadata = response.get("Metadata") or {}
    expected_sha = str(metadata.get("sha256") or "").strip()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if expected_sha and expected_sha != actual_sha:
        raise RuntimeError(f"Recovery backup integrity mismatch: {key}")
    return state


def restore_production_state(
    *,
    store: R2StateStore,
    backup_key: str,
    observed_at: str,
    run_id: str,
) -> dict[str, Any]:
    """Restore a validated backup as a new monotonic production generation."""
    _assert_production_store(store)
    if not observed_at or not run_id:
        raise ValueError("observed_at and run_id are required")

    backup = load_backup_state(store, backup_key)
    current = store.load_current(allow_missing=False)
    restored = copy.deepcopy(backup)
    restored["generation"] = int(current.state.get("generation") or 0) + 1
    restored["updated_at"] = observed_at
    restored["last_run_id"] = f"recovery:{run_id}"
    restored["writer_role"] = WRITER_ROLE
    validate_state(restored)

    published = store.publish(
        restored,
        expected_etag=current.etag,
        run_id=f"recovery-{run_id}",
    )
    verified = store.load_current(allow_missing=False)
    if state_sha256(verified.state) != state_sha256(restored):
        raise RuntimeError("Recovery post-write verification failed")

    return {
        "status": "PASS",
        "backup_key": _validate_backup_key(backup_key),
        "backup_generation": int(backup.get("generation") or 0),
        "previous_generation": int(current.state.get("generation") or 0),
        "restored_generation": int(restored["generation"]),
        "jobs_restored": len(restored.get("jobs") or {}),
        "current_key": store.current_key,
        "publish": published,
    }
