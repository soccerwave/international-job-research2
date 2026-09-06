from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.live_shards import SHARD_IDS
from src.runtime.preprod import persist_preprod_state, run_preprod_finalization
from src.state.r2_store import R2StateStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _plus_one_second(value: str) -> str:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed.astimezone(timezone.utc) + timedelta(seconds=1)).replace(microsecond=0).isoformat()


def _safe_stage10_prefix(prefix: str) -> str:
    clean = str(prefix or "").strip("/")
    if not clean.startswith("acceptance/stage10/"):
        raise RuntimeError(
            "Stage 10 R2 runs must use an isolated prefix beginning with acceptance/stage10/. "
            "The production state/current key is intentionally inaccessible from this CLI."
        )
    if len(clean.split("/")) < 3 or not clean.split("/")[-1].strip():
        raise RuntimeError("Stage 10 R2 acceptance prefix must include a unique run suffix")
    return clean


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Stage 10 pre-production central finalization")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--output-root", default="artifacts")
    parser.add_argument("--observed-at", default=None)
    parser.add_argument("--state-backend", choices=("LOCAL", "R2"), default="LOCAL")
    parser.add_argument("--state-path", default=None)
    parser.add_argument("--r2-prefix", default=None)
    parser.add_argument("--allow-bootstrap", action="store_true")
    parser.add_argument(
        "--expect-stage10-shards",
        action="store_true",
        help="Require all configured Stage 10 shard artifacts to be present; missing shards surface as PARTIAL_PASS.",
    )
    parser.add_argument(
        "--verify-r2-replay",
        action="store_true",
        help="After the first isolated R2 write, replay the exact canonical set and require all records to become SEEN.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    observed_at = args.observed_at or _now_iso()
    artifact_root = Path(args.artifact_root)
    output_root = Path(args.output_root)
    store = None
    state_path = Path(args.state_path) if args.state_path else output_root / args.run_id / "local-state" / "state.json"

    if args.state_backend == "R2":
        if not args.r2_prefix:
            raise RuntimeError("--r2-prefix is required for Stage 10 R2 runs")
        store = R2StateStore.from_env(prefix=_safe_stage10_prefix(args.r2_prefix))

    result = run_preprod_finalization(
        run_id=args.run_id,
        artifact_root=artifact_root,
        output_root=output_root,
        observed_at=observed_at,
        state_backend=args.state_backend,
        state_path=state_path if args.state_backend == "LOCAL" else None,
        r2_store=store,
        allow_bootstrap=args.allow_bootstrap,
        expected_shards=SHARD_IDS if args.expect_stage10_shards else None,
    )

    acceptance = {"initial": result}
    if args.verify_r2_replay and args.state_backend == "R2" and result.get("status") in {"PASS", "PARTIAL_PASS"}:
        canonical_path = output_root / args.run_id / "preprod" / "canonical_records.json"
        records = json.loads(canonical_path.read_text(encoding="utf-8"))
        expected = len(records)

        initial_state = result.get("state") or {}
        fresh_identity_ok = (
            int(initial_state.get("NEW") or 0) == expected
            and int(initial_state.get("SEEN") or 0) == 0
            and int(initial_state.get("MATERIALLY_CHANGED") or 0) == 0
            and int(initial_state.get("REOPENED") or 0) == 0
            and int(initial_state.get("state_jobs") or 0) == expected
            and bool((result.get("state_identity_projection") or {}).get("state_id_cardinality_matches_records"))
        )
        acceptance["fresh_state_identity"] = {
            "status": "PASS" if fresh_identity_ok else "FAIL",
            "expected_records": expected,
            "summary": initial_state,
            "projection": result.get("state_identity_projection") or {},
        }
        if not fresh_identity_ok:
            print(json.dumps(acceptance, ensure_ascii=False, indent=2))
            return 3

        replay, replay_projection = persist_preprod_state(
            records,
            state_backend="R2",
            r2_store=store,
            observed_at=_plus_one_second(observed_at),
            run_id=f"{args.run_id}-replay",
            allow_bootstrap=False,
        )
        replay_ok = (
            int(replay.summary.get("SEEN") or 0) == expected
            and int(replay.summary.get("NEW") or 0) == 0
            and int(replay.summary.get("MATERIALLY_CHANGED") or 0) == 0
            and int(replay.summary.get("REOPENED") or 0) == 0
            and int(replay.summary.get("not_observed_inferred_closed") or 0) == 0
            and int(replay.summary.get("state_jobs") or 0) == expected
            and bool(replay_projection.get("state_id_cardinality_matches_records"))
        )
        acceptance["r2_replay"] = {
            "status": "PASS" if replay_ok else "FAIL",
            "summary": replay.summary,
            "persistence": replay.persistence,
            "projection": replay_projection,
        }
        replay_path = output_root / args.run_id / "preprod" / "state_replay.json"
        replay_path.write_text(json.dumps(acceptance["r2_replay"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not replay_ok:
            print(json.dumps(acceptance, ensure_ascii=False, indent=2))
            return 3

    acceptance_path = output_root / args.run_id / "preprod" / "stage10_acceptance.json"
    acceptance_path.parent.mkdir(parents=True, exist_ok=True)
    acceptance_path.write_text(json.dumps(acceptance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(acceptance, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"PASS", "PARTIAL_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
