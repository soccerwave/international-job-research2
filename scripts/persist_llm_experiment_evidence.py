from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.llm.experiment_evidence import (
    R2ExperimentEvidenceStore,
    build_experiment_evidence_bundle,
    serialize_experiment_evidence,
)
from src.reporting.llm_shadow_excel import load_full_evaluation_records
from src.reporting.user_excel import load_canonical_records


def _load_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON array or JSONL")
        return [row for row in payload if isinstance(row, dict)]
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        row = json.loads(raw)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no} is not a JSON object")
        rows.append(row)
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and optionally persist one immutable LLM experiment evidence bundle")
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--full-evaluations", type=Path, required=True)
    parser.add_argument("--rescue-triage", type=Path, required=True)
    parser.add_argument("--disagreements", type=Path, required=True)
    parser.add_argument("--failures", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--candidate-profile-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--persist-r2", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    bundle = build_experiment_evidence_bundle(
        run_id=args.run_id,
        run_date=args.run_date,
        model=args.model,
        candidate_profile_version=args.candidate_profile_version,
        canonical_jobs=load_canonical_records(args.records),
        full_evaluation_records=load_full_evaluation_records(args.full_evaluations),
        rescue_triage_records=_load_rows(args.rescue_triage),
        disagreement_rows=_load_rows(args.disagreements),
        failures=_load_rows(args.failures),
    )

    payload = serialize_experiment_evidence(bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)

    durable = None
    if args.persist_r2:
        stored = R2ExperimentEvidenceStore.from_env().persist(bundle)
        durable = {
            "key": stored.key,
            "sha256": stored.sha256,
            "bytes": stored.bytes,
            "etag": stored.etag,
        }

    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(args.output),
                "run_id": bundle["run_id"],
                "run_date": bundle["run_date"],
                "model": bundle["model"],
                "summary": bundle["summary"],
                "persisted_r2": bool(args.persist_r2),
                "durable_evidence": durable,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
