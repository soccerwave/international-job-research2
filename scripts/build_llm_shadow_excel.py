from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.reporting.llm_shadow_excel import (
    build_llm_shadow_report_rows,
    build_llm_shadow_xlsx,
    load_full_evaluation_records,
)
from src.reporting.user_excel import load_canonical_records


def _load_id_set(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        values = payload.get("job_ids")
    else:
        values = payload
    if not isinstance(values, list):
        raise ValueError("MAIN job ID file must be a JSON list or an object with job_ids")
    return {str(value).strip() for value in values if str(value).strip()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the L7.2 three-sheet LLM shadow Excel report")
    parser.add_argument("--records", type=Path, required=True, help="Canonical jobs JSON array")
    parser.add_argument("--main-job-ids", type=Path, required=True, help="JSON list of MAIN canonical job IDs")
    parser.add_argument("--full-evaluations", type=Path, required=True, help="L7.1 FullEvaluationRecord JSONL")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    records = load_canonical_records(args.records)
    main_ids = _load_id_set(args.main_job_ids)
    full_records = load_full_evaluation_records(args.full_evaluations)

    rows = build_llm_shadow_report_rows(
        records,
        main_job_ids=main_ids,
        full_evaluation_records=full_records,
    )
    build_llm_shadow_xlsx(
        records,
        args.output,
        main_job_ids=main_ids,
        full_evaluation_records=full_records,
    )

    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(args.output),
                "sheets": ["MAIN", "LLM_RESCUED", "DISAGREEMENTS"],
                "main_rows": len(rows.main),
                "llm_rescued_rows": len(rows.llm_rescued),
                "disagreement_rows": len(rows.disagreements),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
