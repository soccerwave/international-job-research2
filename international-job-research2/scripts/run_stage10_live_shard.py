from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.live_shards import SHARD_IDS, run_live_shard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Stage 10 pre-production live collection shard")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--shard-id", required=True, choices=SHARD_IDS)
    parser.add_argument("--output-root", default="artifacts")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    diagnostic = run_live_shard(
        run_id=args.run_id,
        shard_id=args.shard_id,
        output_root=Path(args.output_root),
    )
    print(json.dumps(diagnostic.to_dict(), ensure_ascii=False, indent=2))
    return 2 if diagnostic.status.value == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
