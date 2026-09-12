from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reporting.report import build_reporting_payload, build_xlsx, write_summary_json
from src.runtime.canonicalizer import canonicalize_records
from src.runtime.finalizer import finalize_run
from src.runtime.preprod import (
    _load_fanin_records,
    _validate_canonical,
    apply_central_availability,
    collect_source_diagnostics,
    evaluate_canonical_records,
)
from src.runtime.state_projection import build_state_identity_projection


def _timed(name: str, fn):
    started = time.perf_counter()
    value = fn()
    elapsed = time.perf_counter() - started
    print(json.dumps({"phase": name, "elapsed_seconds": round(elapsed, 3)}), flush=True)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only phase timing for a completed production shard set")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--output-root", default="diagnostics")
    parser.add_argument("--observed-at", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    artifact_root = Path(args.artifact_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    fanin = _timed(
        "fanin",
        lambda: finalize_run(run_id=args.run_id, artifact_root=artifact_root, output_root=output_root),
    )
    diagnostics = _timed(
        "source_diagnostics",
        lambda: collect_source_diagnostics(run_id=args.run_id, artifact_root=artifact_root),
    )
    raw_records = _timed(
        "load_fanin_records",
        lambda: _load_fanin_records(run_id=args.run_id, output_root=output_root),
    )
    canonical, canonical_summary = _timed("canonicalization", lambda: canonicalize_records(raw_records))
    _timed(
        "availability",
        lambda: [apply_central_availability(record, observed_at=args.observed_at) for record in canonical],
    )
    _timed("evaluation", lambda: evaluate_canonical_records(canonical))
    _timed("schema_validation", lambda: _validate_canonical(canonical))
    projected, projection_summary = _timed("state_identity_projection", lambda: build_state_identity_projection(canonical))

    payload = _timed(
        "report_payload",
        lambda: build_reporting_payload(
            canonical,
            run_id=args.run_id,
            generated_at=args.observed_at,
            state_summary={"records_observed": len(projected)},
            source_diagnostics=diagnostics,
        ),
    )
    report = _timed(
        "xlsx_build",
        lambda: build_xlsx(payload, output_root / args.run_id / "diagnostic_report.xlsx"),
    )
    summary = _timed(
        "report_summary_write",
        lambda: write_summary_json(payload, output_root / args.run_id / "diagnostic_report_summary.json"),
    )

    print(json.dumps({
        "status": "PASS",
        "run_id": args.run_id,
        "fanin_status": fanin.status.value,
        "raw_records": len(raw_records),
        "canonical_records": len(canonical),
        "canonical_summary": canonical_summary,
        "projection_summary": projection_summary,
        "report": str(report),
        "summary": str(summary),
        "authoritative_state_mutation": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
