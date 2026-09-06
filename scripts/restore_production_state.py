from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.recovery import restore_production_state
from src.state.r2_store import R2StateStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore authoritative production state from an immutable R2 backup")
    parser.add_argument("--backup-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--observed-at", default=None)
    parser.add_argument("--confirm", required=True, help="Must be exactly RESTORE")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.confirm != "RESTORE":
        raise SystemExit("Recovery refused: --confirm must be exactly RESTORE")
    store = R2StateStore.from_env(prefix="")
    result = restore_production_state(
        store=store,
        backup_key=args.backup_key,
        observed_at=args.observed_at or _now_iso(),
        run_id=args.run_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
