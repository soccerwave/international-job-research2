from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.state.r2_migration_retention import apply_migration_retention, plan_migration_retention
from src.state.r2_store import R2StateStore


def mb(value: int) -> float:
    return round(value / 1024 / 1024, 2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-days", type=int, default=14)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    store = R2StateStore.from_env()
    plan = plan_migration_retention(store, max_age_days=args.max_age_days)
    payload = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "max_age_days": args.max_age_days,
        "snapshots": plan.snapshots,
        "delete_count": len(plan.delete_keys),
        "delete_mb": mb(plan.delete_bytes),
        "kept_mb": mb(plan.kept_bytes),
        "delete_keys": list(plan.delete_keys),
    }
    if args.apply:
        payload["result"] = apply_migration_retention(store, plan)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
