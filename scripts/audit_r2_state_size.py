from __future__ import annotations

import copy
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.state.engine import state_bytes
from src.state.r2_store import R2StateStore


def compact_bytes(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def mb(value: int) -> float:
    return round(value / 1024 / 1024, 2)


def main() -> int:
    store = R2StateStore.from_env()
    loaded = store.load_current(allow_missing=False)
    state = loaded.state
    jobs = state.get("jobs") or {}

    total_pretty = len(state_bytes(state))
    total_compact = compact_bytes(state)

    totals = Counter()
    alias_counts = []
    top_entries = []

    for state_id, entry in jobs.items():
        entry_bytes = compact_bytes(entry)
        aliases = entry.get("aliases") or []
        snapshot = entry.get("last_snapshot") or {}

        totals["entries"] += entry_bytes
        totals["aliases"] += compact_bytes(aliases)
        totals["last_snapshot"] += compact_bytes(snapshot)
        totals["entry_metadata"] += compact_bytes({k: v for k, v in entry.items() if k not in {"aliases", "last_snapshot"}})
        alias_counts.append(len(aliases))

        for key, value in snapshot.items():
            totals[f"snapshot.{key}"] += compact_bytes(value)

        top_entries.append((entry_bytes, state_id, len(aliases)))

    hypothetical = copy.deepcopy(state)
    dimensions_removed_jobs = 0
    for entry in (hypothetical.get("jobs") or {}).values():
        snapshot = entry.get("last_snapshot") or {}
        if "evaluation_dimensions" in snapshot:
            snapshot.pop("evaluation_dimensions", None)
            dimensions_removed_jobs += 1
    without_dimensions_compact = compact_bytes(hypothetical)

    top_entries.sort(reverse=True)
    alias_counts.sort()

    def percentile(values, p):
        if not values:
            return 0
        index = min(len(values) - 1, max(0, round((len(values) - 1) * p)))
        return values[index]

    snapshot_fields = [
        {"field": key.removeprefix("snapshot."), "mb": mb(value), "bytes": value}
        for key, value in totals.items()
        if key.startswith("snapshot.")
    ]
    snapshot_fields.sort(key=lambda row: row["bytes"], reverse=True)

    payload = {
        "generation": state.get("generation"),
        "state_jobs": len(jobs),
        "total_pretty_mb": mb(total_pretty),
        "total_compact_mb": mb(total_compact),
        "pretty_overhead_mb": mb(total_pretty - total_compact),
        "component_mb": {
            "entries_compact": mb(totals["entries"]),
            "aliases": mb(totals["aliases"]),
            "last_snapshot": mb(totals["last_snapshot"]),
            "entry_metadata": mb(totals["entry_metadata"]),
        },
        "hypothetical_without_evaluation_dimensions": {
            "jobs_affected": dimensions_removed_jobs,
            "compact_mb": mb(without_dimensions_compact),
            "savings_mb": mb(total_compact - without_dimensions_compact),
            "savings_percent": round((total_compact - without_dimensions_compact) * 100 / total_compact, 2) if total_compact else 0,
        },
        "alias_count": {
            "min": alias_counts[0] if alias_counts else 0,
            "median": percentile(alias_counts, 0.5),
            "p95": percentile(alias_counts, 0.95),
            "p99": percentile(alias_counts, 0.99),
            "max": alias_counts[-1] if alias_counts else 0,
            "total": sum(alias_counts),
        },
        "snapshot_field_sizes": snapshot_fields,
        "largest_entries": [
            {"state_id": state_id, "kb": round(size / 1024, 2), "alias_count": alias_count}
            for size, state_id, alias_count in top_entries[:20]
        ],
    }

    print(json.dumps(payload, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
