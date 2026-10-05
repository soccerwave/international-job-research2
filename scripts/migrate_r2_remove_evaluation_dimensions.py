from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.state.engine import validate_state
from src.state.r2_store import R2StateStore, compact_state_bytes, state_for_storage


def mb(value: int) -> float:
    return round(value / 1024 / 1024, 2)


def raw_compact_bytes(state: dict) -> bytes:
    validate_state(state)
    return (json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def plan(state: dict) -> dict:
    validate_state(state)
    durable = state_for_storage(state)
    affected = 0
    for entry in (state.get("jobs") or {}).values():
        snapshot = entry.get("last_snapshot") or {}
        if "evaluation_dimensions" in snapshot:
            affected += 1
    before = raw_compact_bytes(state)
    after = compact_state_bytes(state)
    return {
        "affected_jobs": affected,
        "before_bytes": len(before),
        "after_bytes": len(after),
        "saved_bytes": len(before) - len(after),
        "before_mb": mb(len(before)),
        "after_mb": mb(len(after)),
        "saved_mb": mb(len(before) - len(after)),
        "durable_state": durable,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    store = R2StateStore.from_env()
    loaded = store.load_current(allow_missing=False)
    migration = plan(loaded.state)

    result = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "source_generation": loaded.state.get("generation"),
        "affected_jobs": migration["affected_jobs"],
        "before_mb": migration["before_mb"],
        "after_mb": migration["after_mb"],
        "saved_mb": migration["saved_mb"],
    }

    if not args.apply:
        print(json.dumps(result, indent=2))
        return 0

    if migration["affected_jobs"] == 0:
        result["status"] = "NOOP_ALREADY_MIGRATED"
        print(json.dumps(result, indent=2))
        return 0

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source_generation = int(loaded.state["generation"])
    safe_stamp = re.sub(r"[^0-9TZ-]", "", now)

    # Preserve an immutable exact pre-migration snapshot before changing authoritative state.
    pre_payload = raw_compact_bytes(loaded.state)
    pre_digest = hashlib.sha256(pre_payload).hexdigest()
    pre_key = store.key(f"state/migrations/evaluation-dimensions/g{source_generation:08d}-before-{safe_stamp}.json")
    pre_metadata = {
        "sha256": pre_digest,
        "state-version": str(loaded.state["state_version"]),
        "generation": str(source_generation),
        "migration": "remove-evaluation-dimensions",
    }
    store._put(key=pre_key, payload=pre_payload, headers={"If-None-Match": "*"}, metadata=pre_metadata)

    migrated = copy.deepcopy(migration["durable_state"])
    migrated["generation"] = source_generation + 1
    migrated["updated_at"] = now
    migrated["last_run_id"] = "migration-remove-evaluation-dimensions"
    validate_state(migrated)

    published = store.publish(
        migrated,
        expected_etag=loaded.etag,
        run_id="migration-remove-evaluation-dimensions",
    )
    verified = store.load_current(allow_missing=False)
    remaining = sum(
        1
        for entry in (verified.state.get("jobs") or {}).values()
        if "evaluation_dimensions" in (entry.get("last_snapshot") or {})
    )
    if remaining:
        raise RuntimeError(f"Migration verification failed: {remaining} jobs still contain evaluation_dimensions")

    result.update({
        "status": "APPLIED",
        "pre_migration_key": pre_key,
        "new_generation": verified.state.get("generation"),
        "remaining_jobs_with_dimensions": remaining,
        "backup_key": published.get("backup_key"),
        "current_key": published.get("current_key"),
    })
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
