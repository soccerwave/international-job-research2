from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.reporting.report import build_reporting_payload, build_xlsx, record_to_row, write_summary_json
from src.reporting.telegram import TelegramPermanentError, check_configuration, format_summary, send_report


def _record(
    job_id: str,
    *,
    rec: str = "APPLY",
    event: str = "NEW",
    country: str = "Netherlands",
    source_key: str = "academictransfer",
    source_status: str = "OPEN",
    detail_status: str = "FULL",
    disposition: str = "ELIGIBLE_FOR_EVALUATION",
) -> dict:
    return {
        "source_record_id": job_id,
        "canonical_id": f"canon-{job_id}",
        "source": {
            "source_key": source_key,
            "provider": source_key,
            "source_job_id": job_id,
            "detail_url": f"https://example.org/jobs/{job_id}",
            "apply_url": f"https://example.org/apply/{job_id}",
            "source_status": source_status,
        },
        "position": {
            "title_raw": f"Postdoctoral Researcher {job_id}",
            "institution_raw": "Example University",
            "department": "Human Movement Sciences",
            "role_family": "POSTDOC",
            "role_level": "POSTDOC",
        },
        "location": {"country_code": "NL", "country_name": country, "city": "Amsterdam"},
        "dates": {"deadline_at": "2026-10-15", "deadline_status": "KNOWN"},
        "description": {"detail_status": detail_status, "full_jd": "exercise neuroscience stress " * 40},
        "raw_extra": {
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": rec,
                "pre_evaluation_disposition": disposition,
                "role_family": "POSTDOC",
                "dimensions": {
                    "scientific": "STRONG",
                    "level": "MATCH",
                    "methods": "MATCH",
                    "language": "COMPATIBLE",
                    "mobility": "POTENTIALLY_VIABLE",
                    "registration": "NOT_REQUIRED",
                    "contract": "ACCEPTABLE",
                },
                "review_codes": ["UNCLEAR_DOMAIN"] if rec == "REVIEW" else [],
                "blocker_codes": ["ROLE_STUDENT"] if rec == "SKIP" else [],
                "reason": "Synthetic evaluator reason.",
            },
            "state": {
                "state_version": "STATE_SCHEMA_V1.0.0",
                "seen_status": event,
                "quality_events": [],
                "change_reasons": ["deadline_at"] if event == "MATERIALLY_CHANGED" else [],
                "lifecycle_status": source_status,
            },
        },
    }


class Stage9ReportingTests(unittest.TestCase):
    def test_record_to_row_preserves_multidimensional_evaluation(self):
        row = record_to_row(_record("1"))
        self.assertEqual(row["recommendation"], "APPLY")
        self.assertEqual(row["scientific"], "STRONG")
        self.assertEqual(row["mobility"], "POTENTIALLY_VIABLE")
        self.assertEqual(row["url"], "https://example.org/apply/1")

    def test_closed_jobs_are_not_current_actionable(self):
        payload = build_reporting_payload([_record("1"), _record("2", source_status="CLOSED")], run_id="r1")
        self.assertEqual(payload["summary"]["current_actionable"], 1)
        self.assertEqual(len(payload["current_actionable"]), 1)

    def test_today_contains_only_change_events(self):
        records = [_record("1", event="NEW"), _record("2", event="SEEN"), _record("3", event="REOPENED")]
        payload = build_reporting_payload(records, run_id="r2")
        self.assertEqual(payload["summary"]["today_actionable"], 2)
        self.assertEqual({row["seen_status"] for row in payload["today_actionable"]}, {"NEW", "REOPENED"})

    def test_review_queue_is_fail_open_for_unresolved_detail(self):
        records = [_record("1", rec="APPLY", detail_status="FETCH_FAILED"), _record("2", rec="REVIEW")]
        payload = build_reporting_payload(records, run_id="r3")
        self.assertEqual(payload["summary"]["review_queue"], 2)

    def test_summary_keeps_country_as_dimension_not_partition(self):
        records = [_record("1", country="Netherlands"), _record("2", country="Germany")]
        payload = build_reporting_payload(records, run_id="r4")
        self.assertEqual(dict(payload["summary"]["top_actionable_countries"]), {"Netherlands": 1, "Germany": 1})

    def test_source_diagnostics_can_include_zero_observation_failure(self):
        payload = build_reporting_payload(
            [_record("1")],
            run_id="r5",
            source_diagnostics={"academictransfer": {"status": "OK"}, "cnrs": {"status": "ERROR", "error": "timeout"}},
        )
        by_key = {row["source_key"]: row for row in payload["sources"]}
        self.assertEqual(by_key["cnrs"]["observed"], 0)
        self.assertEqual(by_key["cnrs"]["status"], "ERROR")
        self.assertEqual(payload["summary"]["source_health"]["ERROR"], 1)

    def test_state_summary_is_reported_without_recomputing_state(self):
        payload = build_reporting_payload(
            [_record("1")], run_id="r6", state_summary={"generation": 7, "state_jobs": 42, "DETAIL_RESOLVED": 2}
        )
        self.assertEqual(payload["summary"]["state_generation"], 7)
        self.assertEqual(payload["summary"]["state_jobs"], 42)
        self.assertEqual(payload["summary"]["quality_events"]["DETAIL_RESOLVED"], 2)

    def test_xlsx_has_fixed_human_review_sheets_and_no_country_sheets(self):
        payload = build_reporting_payload([_record("1")], run_id="r7")
        with tempfile.TemporaryDirectory() as td:
            path = build_xlsx(payload, Path(td) / "report.xlsx")
            with zipfile.ZipFile(path) as archive:
                workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
            expected = ["SUMMARY", "TODAY_ACTIONABLE", "CURRENT_ACTIONABLE", "REVIEW_QUEUE", "LOW_PRIORITY", "AUDIT", "SOURCES"]
            for name in expected:
                self.assertIn(f'name="{name}"', workbook_xml)
            self.assertNotIn('name="Netherlands"', workbook_xml)

    def test_summary_json_contains_reporting_contract(self):
        payload = build_reporting_payload([_record("1")], run_id="r8", generated_at="2026-09-04T20:00:00+00:00")
        with tempfile.TemporaryDirectory() as td:
            path = write_summary_json(payload, Path(td) / "summary.json")
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["reporting_version"], "REPORTING_V1.0.0")
        self.assertEqual(data["run_id"], "r8")

    def test_telegram_summary_prioritizes_decision_signals(self):
        payload = build_reporting_payload([_record("1", rec="STRONG_APPLY", event="MATERIALLY_CHANGED")], run_id="r9")
        text = format_summary(payload["summary"])
        self.assertIn("STRONG: 1", text)
        self.assertIn("Changed: 1", text)
        self.assertIn("Current actionable: 1", text)

    def test_telegram_missing_credentials_is_permanent_configuration_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(TelegramPermanentError):
                check_configuration()

    def test_telegram_document_only_when_actionable_change_or_forced(self):
        summary = build_reporting_payload([_record("1", event="SEEN")], run_id="r10")["summary"]
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.xlsx"
            report.write_bytes(b"PK synthetic")
            calls = []
            with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_IDS": "1"}, clear=True):
                with patch("src.reporting.telegram._post", side_effect=lambda method, **kwargs: calls.append(method) or {"ok": True}):
                    send_report(summary, report)
            self.assertEqual(calls, ["sendMessage"])


if __name__ == "__main__":
    unittest.main()
