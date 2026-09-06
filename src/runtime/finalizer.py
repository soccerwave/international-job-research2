from __future__ import annotations

import argparse
import json
from pathlib import Path

from .artifacts import atomic_create_bytes, verify_shard_bundle
from .contracts import FinalizerStatus, FinalizerSummary, utc_now_iso

FINALIZER_CONTRACT_VERSION = "FINALIZER_FANIN_CONTRACT_V1.0.0"


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def finalize_run(*, run_id: str, artifact_root: Path, output_root: Path) -> FinalizerSummary:
    started_at = utc_now_iso()
    run_dir = artifact_root / run_id / "shards"
    manifest_paths = sorted(run_dir.glob("*/manifest.json")) if run_dir.exists() else []

    accepted_shards: list[str] = []
    rejected_shards: list[dict[str, str]] = []
    records: list[dict] = []

    for manifest_path in manifest_paths:
        shard_dir = manifest_path.parent
        try:
            manifest, shard_records, _ = verify_shard_bundle(shard_dir)
            if manifest.run_id != run_id:
                raise ValueError(f"manifest run_id {manifest.run_id!r} does not match {run_id!r}")
            if manifest.status.value == "ERROR":
                raise ValueError("shard status is ERROR")
            accepted_shards.append(manifest.shard_id)
            records.extend(shard_records)
        except Exception as exc:
            rejected_shards.append({"shard_dir": shard_dir.name, "reason": f"{type(exc).__name__}: {exc}"})

    if not manifest_paths:
        status = FinalizerStatus.ERROR
    elif rejected_shards:
        status = FinalizerStatus.PARTIAL if accepted_shards else FinalizerStatus.ERROR
    else:
        status = FinalizerStatus.OK

    output_dir = output_root / run_id / "finalizer"
    summary = FinalizerSummary(
        contract_version=FINALIZER_CONTRACT_VERSION,
        run_id=run_id,
        status=status,
        started_at=started_at,
        finished_at=utc_now_iso(),
        manifests_seen=len(manifest_paths),
        shards_accepted=len(accepted_shards),
        shards_rejected=len(rejected_shards),
        records_loaded=len(records),
        records_emitted=len(records),
        accepted_shards=accepted_shards,
        rejected_shards=rejected_shards,
        warnings=["Stage 4 fan-in only: cross-source dedupe/evaluation/state are intentionally not implemented yet."],
    )

    atomic_create_bytes(output_dir / "records.json", _json_bytes(records))
    atomic_create_bytes(output_dir / "summary.json", _json_bytes(summary.to_dict()))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fan in immutable shard outputs")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--output-root", default="artifacts")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = finalize_run(
        run_id=args.run_id,
        artifact_root=Path(args.artifact_root),
        output_root=Path(args.output_root),
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False))
    return 0 if summary.status != FinalizerStatus.ERROR else 2


if __name__ == "__main__":
    raise SystemExit(main())
