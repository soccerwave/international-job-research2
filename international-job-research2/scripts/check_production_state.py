from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.production import assert_production_store
from src.state.r2_store import R2StateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check authoritative production state readiness")
    parser.add_argument("--github-output", default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = R2StateStore.from_env(prefix="")
    assert_production_store(store)
    loaded = store.load_current(allow_missing=True)
    result = {
        "state_exists": bool(loaded.exists),
        "generation": int((loaded.state or {}).get("generation") or 0),
        "current_key": store.current_key,
    }
    output_path = args.github_output or os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"state_exists={'true' if loaded.exists else 'false'}\n")
            handle.write(f"generation={result['generation']}\n")
            handle.write(f"current_key={store.current_key}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
