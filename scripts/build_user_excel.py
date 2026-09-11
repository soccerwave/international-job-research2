from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.evaluation.calibrated_e021 import EVALUATOR_VERSION, with_calibrated_evaluation
from src.reporting.report import record_to_row
from src.reporting.user_excel import build_review_rows, build_user_rows, build_user_xlsx, load_canonical_records

ACTIONABLE = {"STRONG_APPLY", "APPLY", "REVIEW"}
CHANGE_EVENTS = {"NEW", "MATERIALLY_CHANGED", "REOPENED"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the clean International academic job Excel for human use")
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-summary", type=Path)
    parser.add_argument("--summary-out", type=Path)
    return parser


def build_user_summary(
    records: list[dict],
    base_summary: dict,
    *,
    review_rows: list[dict] | None = None,
) -> dict:
    recommendation_counts: Counter[str] = Counter()
    current_actionable = 0
    today_actionable = 0
    review_queue = 0
    low_priority = 0

    for record in records:
        evaluation = ((record.get("raw_extra") or {}).get("evaluation") or {})
        calibrated = record if str(evaluation.get("evaluator_version") or "") == EVALUATOR_VERSION else with_calibrated_evaluation(record)
        row = record_to_row(calibrated)
        priority = str(row.get("recommendation") or "REVIEW").upper()
        lifecycle = str(row.get("lifecycle_status") or "UNKNOWN").upper()
        seen_status = str(row.get("seen_status") or "").upper()
        recommendation_counts[priority] += 1
        if lifecycle == "CLOSED":
            continue
        if priority in ACTIONABLE:
            current_actionable += 1
            if seen_status in CHANGE_EVENTS:
                today_actionable += 1
        if priority == "REVIEW":
            review_queue += 1
        elif priority == "LOW_PRIORITY":
            low_priority += 1

    summary = dict(base_summary)
    summary["reporting_version"] = "CONTROL_PLANE_USER_REPORT_E021_E11_REVIEW_V1"
    summary["base_reporting_version"] = base_summary.get("reporting_version")
    summary["evaluator_version"] = EVALUATOR_VERSION
    summary["recommendations"] = {
        key: int(recommendation_counts.get(key, 0))
        for key in ("STRONG_APPLY", "APPLY", "REVIEW", "LOW_PRIORITY", "SKIP")
    }
    summary["current_actionable"] = current_actionable
    summary["today_actionable"] = today_actionable
    summary["review_queue"] = review_queue
    summary["low_priority"] = low_priority
    summary["skipped"] = int(recommendation_counts.get("SKIP", 0))
    summary["calibration"] = {
        "mode": "E0.2.1_CALIBRATED_SHADOW",
        "production_evaluator_unchanged": True,
        "audit_workbook_preserves_e0_1": True,
        "clean_excel_contains": ["STRONG_APPLY", "APPLY", "REVIEW"],
    }
    additional = review_rows if review_rows is not None else build_review_rows(records)
    summary["review_more_count"] = len(additional)
    summary["review_more_types"] = dict(Counter(row["review_type"] for row in additional))
    summary["review_more_changes"] = sum(row["seen_status"] in CHANGE_EVENTS for row in additional)
    summary["total_visible"] = current_actionable + len(additional)
    summary["calibration"]["review_more_evaluator"] = "E1.1_RECALL_FIRST_FINAL_CANDIDATE"
    return summary


def main() -> int:
    args = build_parser().parse_args()
    records = load_canonical_records(args.records)
    calibrated_records = [with_calibrated_evaluation(record) for record in records]
    rows = build_user_rows(calibrated_records)
    review_rows = build_review_rows(calibrated_records)
    build_user_xlsx(calibrated_records, args.output, rows=rows, review_rows=review_rows)
    counts: dict[str, int] = {}
    for row in rows:
        key = row["recommendation"]
        counts[key] = counts.get(key, 0) + 1

    summary_path = None
    if args.base_summary or args.summary_out:
        if not args.base_summary or not args.summary_out:
            raise SystemExit("--base-summary and --summary-out must be supplied together")
        base_summary = json.loads(args.base_summary.read_text(encoding="utf-8"))
        user_summary = build_user_summary(calibrated_records, base_summary, review_rows=review_rows)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(user_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary_path = str(args.summary_out)

    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(args.output),
                "summary": summary_path,
                "evaluator_version": EVALUATOR_VERSION,
                "rows": len(rows),
                "review_more_rows": len(review_rows),
                "sheets": ["JOBS", "REVIEW_MORE"],
                "priorities": counts,
                "columns": ["Priority", "Title", "Country", "Role", "Institution", "City", "Deadline", "Link"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

