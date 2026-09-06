from __future__ import annotations

import argparse
import importlib
import time
from pathlib import Path
from typing import Any, Callable

from .artifacts import write_shard_bundle
from .contracts import ShardDiagnostic, ShardStatus, normalize_vacancy_records, utc_now_iso

Collector = Callable[[], list[dict[str, Any]]]


def load_callable(target: str) -> Collector:
    module_name, func_name = target.split(":", 1)
    module = importlib.import_module(module_name)
    collector = getattr(module, func_name)
    if not callable(collector):
        raise TypeError(f"collector target is not callable: {target}")
    return collector


def run_shard(
    *,
    run_id: str,
    shard_id: str,
    source_ids: list[str],
    collector: Collector,
    output_root: Path,
    producer_version: str | None = None,
) -> int:
    started_at = utc_now_iso()
    start = time.monotonic()
    warnings: list[str] = []
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    status = ShardStatus.OK

    try:
        records = normalize_vacancy_records(collector())
    except Exception as exc:  # shard boundary is fail-soft
        status = ShardStatus.ERROR
        errors.append(f"{type(exc).__name__}: {exc}")

    elapsed_ms = int((time.monotonic() - start) * 1000)
    diagnostic = ShardDiagnostic(
        shard_id=shard_id,
        source_ids=source_ids,
        status=status,
        started_at=started_at,
        finished_at=utc_now_iso(),
        elapsed_ms=elapsed_ms,
        records_observed=len(records),
        records_emitted=len(records),
        warnings=warnings,
        errors=errors,
    )

    write_shard_bundle(
        root=output_root,
        run_id=run_id,
        shard_id=shard_id,
        source_ids=source_ids,
        records=records,
        diagnostic=diagnostic,
        producer_version=producer_version,
    )
    return 0 if status != ShardStatus.ERROR else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one independent collection shard")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--shard-id", required=True)
    parser.add_argument("--source-id", action="append", dest="source_ids", required=True)
    parser.add_argument("--collector", required=True, help="Python callable in module:function form")
    parser.add_argument("--output-root", default="artifacts")
    parser.add_argument("--producer-version", default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    collector = load_callable(args.collector)
    return run_shard(
        run_id=args.run_id,
        shard_id=args.shard_id,
        source_ids=args.source_ids,
        collector=collector,
        output_root=Path(args.output_root),
        producer_version=args.producer_version,
    )


if __name__ == "__main__":
    raise SystemExit(main())
