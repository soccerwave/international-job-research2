from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reporting.report import build_reporting_payload, build_xlsx, write_summary_json
from src.reporting.telegram import format_summary


def record(job_id: str, rec: str, event: str, country: str) -> dict:
    detail = "exercise neuroscience stress physical activity cognition " * 40
    return {
        "source_record_id": job_id,
        "canonical_id": f"canonical-{job_id}",
        "source": {
            "source_key": "stage9_smoke",
            "provider": "Stage 9 Smoke",
            "source_job_id": job_id,
            "detail_url": f"https://example.org/jobs/{job_id}",
            "source_status": "OPEN",
        },
        "position": {
            "title_raw": f"Postdoctoral Researcher {job_id}",
            "institution_raw": "Example University",
            "role_family": "POSTDOC",
            "role_level": "POSTDOC",
        },
        "location": {"country_code": country[:2].upper(), "country_name": country, "city": "Example City"},
        "dates": {"deadline_at": "2026-10-15", "deadline_status": "KNOWN"},
        "description": {"detail_status": "FULL", "full_jd": detail},
        "raw_extra": {
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": rec,
                "pre_evaluation_disposition": "POLICY_REVIEW" if rec == "REVIEW" else "ELIGIBLE_FOR_EVALUATION",
                "role_family": "POSTDOC",
                "dimensions": {
                    "scientific": "STRONG", "level": "MATCH", "methods": "MATCH",
                    "language": "COMPATIBLE", "mobility": "POTENTIALLY_VIABLE",
                    "registration": "NOT_REQUIRED", "contract": "ACCEPTABLE",
                },
                "review_codes": ["UNCLEAR_DOMAIN"] if rec == "REVIEW" else [],
                "blocker_codes": [],
                "reason": "Stage 9 deterministic smoke record.",
            },
            "state": {
                "state_version": "STATE_SCHEMA_V1.0.0",
                "seen_status": event,
                "quality_events": [],
                "change_reasons": [],
                "lifecycle_status": "OPEN",
            },
        },
    }


def main() -> None:
    records = [
        record("1", "STRONG_APPLY", "NEW", "Netherlands"),
        record("2", "APPLY", "MATERIALLY_CHANGED", "Germany"),
        record("3", "REVIEW", "SEEN", "Belgium"),
        record("4", "LOW_PRIORITY", "NEW", "Austria"),
        record("5", "SKIP", "NEW", "France"),
    ]
    payload = build_reporting_payload(
        records,
        run_id="stage9-smoke",
        generated_at="2026-09-04T20:00:00+00:00",
        state_summary={"generation": 2, "state_jobs": 5, "DETAIL_RESOLVED": 0, "DETAIL_UNRESOLVED": 0},
        source_diagnostics={"stage9_smoke": {"status": "OK"}},
    )
    out = Path("artifacts/stage9-smoke")
    out.mkdir(parents=True, exist_ok=True)
    xlsx_path = build_xlsx(payload, out / "academic_job_report.xlsx")
    summary_path = write_summary_json(payload, out / "report_summary.json")
    telegram_text = format_summary(payload["summary"])
    (out / "telegram_preview.txt").write_text(telegram_text + "\n", encoding="utf-8")

    with zipfile.ZipFile(xlsx_path) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
    sheets = ["SUMMARY", "TODAY_ACTIONABLE", "CURRENT_ACTIONABLE", "REVIEW_QUEUE", "LOW_PRIORITY", "AUDIT", "SOURCES"]
    if not all(f'name="{name}"' in workbook_xml for name in sheets):
        raise SystemExit("Stage 9 smoke workbook is missing required sheets")
    if payload["summary"]["current_actionable"] != 3 or payload["summary"]["today_actionable"] != 2:
        raise SystemExit("Stage 9 smoke queue counts are incorrect")

    result = {
        "status": "PASS",
        "reporting_version": payload["summary"]["reporting_version"],
        "xlsx": str(xlsx_path),
        "summary": str(summary_path),
        "required_sheets": sheets,
        "current_actionable": 3,
        "today_actionable": 2,
        "telegram_preview": telegram_text,
    }
    (out / "acceptance.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
