from __future__ import annotations

import argparse
import json

from src.state.r2_retention import apply_backup_retention, plan_backup_retention
from src.state.r2_store import R2StateStore


def _mb(value: int) -> float:
    return round(value / 1024 / 1024, 2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely prune old production R2 state backups.")
    parser.add_argument("--max-age-days", type=int, default=7)
    parser.add_argument("--keep-latest", type=int, default=3)
    parser.add_argument("--apply", action="store_true", help="Actually delete candidates. Default is dry-run.")
    args = parser.parse_args()

    store = R2StateStore.from_env()
    plan = plan_backup_retention(
        store,
        max_age_days=args.max_age_days,
        keep_latest=args.keep_latest,
    )
    payload = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "policy": {"max_age_days": args.max_age_days, "keep_latest": args.keep_latest},
        "production_backups": plan.production_backups,
        "protected_latest": list(plan.protected_latest),
        "delete_count": len(plan.delete_keys),
        "delete_mb": _mb(plan.delete_bytes),
        "kept_mb": _mb(plan.kept_bytes),
        "untouched_nonproduction": plan.untouched_nonproduction,
        "delete_keys": list(plan.delete_keys),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if args.apply:
        result = apply_backup_retention(store, plan)
        print(json.dumps({"result": result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
