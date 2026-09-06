from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reporting.report import build_reporting_payload, build_xlsx, write_summary_json


def _load_json(path: Path | None, default):
    if path is None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Stage 9 human-review XLSX and summary JSON")
    parser.add_argument("--records", required=True, help="JSON array of canonical evaluated records annotated by Stage 8 state")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-summary")
    parser.add_argument("--source-diagnostics")
    parser.add_argument("--xlsx", default="artifacts/reporting/academic_job_report.xlsx")
    parser.add_argument("--summary", default="artifacts/reporting/report_summary.json")
    args = parser.parse_args()

    records = _load_json(Path(args.records), [])
    if not isinstance(records, list):
        raise SystemExit("--records must contain a JSON array")
    state_summary = _load_json(Path(args.state_summary), {}) if args.state_summary else {}
    source_diagnostics = _load_json(Path(args.source_diagnostics), {}) if args.source_diagnostics else {}
    payload = build_reporting_payload(
        records,
        run_id=args.run_id,
        state_summary=state_summary,
        source_diagnostics=source_diagnostics,
    )
    xlsx = build_xlsx(payload, Path(args.xlsx))
    summary = write_summary_json(payload, Path(args.summary))
    print(json.dumps({"xlsx": str(xlsx), "summary": str(summary), **payload["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
