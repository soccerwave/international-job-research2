from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.observability import collect_run_observability
from src.runtime.production import run_production_finalization
from src.runtime.production_reporting import rebuild_fresh_bootstrap_report
from src.runtime.production_shards import PRODUCTION_SHARD_IDS
from src.state.r2_store import R2StateStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the V1 authoritative production finalizer")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--output-root", default="artifacts")
    parser.add_argument("--observed-at", default=None)
    parser.add_argument("--allow-bootstrap", action="store_true")
    parser.add_argument(
        "--strict-release",
        action="store_true",
        help="Require all production shards/sources healthy before mutation and enforce the V1 release gate.",
    )
    return parser


def _write_production_summary(*, output_root: Path, run_id: str, result: dict) -> None:
    production_dir = output_root / run_id / "production"
    production_dir.mkdir(parents=True, exist_ok=True)
    production_summary = production_dir / "production_summary.json"
    production_summary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    output_root = Path(args.output_root)
    artifact_root = Path(args.artifact_root)
    store = R2StateStore.from_env(prefix="")
    result = run_production_finalization(
        run_id=args.run_id,
        artifact_root=artifact_root,
        output_root=output_root,
        observed_at=args.observed_at or _now_iso(),
        store=store,
        expected_shards=PRODUCTION_SHARD_IDS,
        allow_bootstrap=args.allow_bootstrap,
        strict_release=args.strict_release,
    )
    result["run_observability"] = collect_run_observability(
        run_id=args.run_id,
        artifact_root=artifact_root,
        expected_shards=PRODUCTION_SHARD_IDS,
    )
    if (
        result.get("status") != "STRICT_PREFLIGHT_FAILED"
        and result.get("state_before_exists") is False
        and str(((result.get("core_result") or {}).get("status") or result.get("status") or "")) == "PASS"
    ):
        result["bootstrap_reporting"] = rebuild_fresh_bootstrap_report(
            output_root=output_root,
            run_id=args.run_id,
        )
    _write_production_summary(output_root=output_root, run_id=args.run_id, result=result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "STRICT_PREFLIGHT_FAILED":
        return 3
    core_status = str(((result.get("core_result") or {}).get("status") or result.get("status") or "ERROR"))
    if args.strict_release:
        return 0 if core_status == "PASS" else 4
    return 0 if core_status in {"PASS", "PARTIAL_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
