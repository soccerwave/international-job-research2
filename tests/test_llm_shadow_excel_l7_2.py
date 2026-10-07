from __future__ import annotations

import copy
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from src.llm.full_evaluation_routing import FullEvaluationRecord, ORIGIN_LLM_RESCUE, ORIGIN_MAIN
from src.reporting.llm_shadow_excel import (
    FAVORABLE_LLM_DECISIONS,
    build_llm_shadow_report_rows,
    build_llm_shadow_xlsx,
)


def canonical(job_id: str, title: str) -> dict:
    return {
        "canonical_id": job_id,
        "source_record_id": f"source:{job_id}",
        "source": {
            "listing_url": f"https://example.org/{job_id}",
            "detail_url": f"https://example.org/{job_id}",
        },
        "position": {
            "title_raw": title,
            "institution_raw": "Example University",
            "role_level": "POSTDOC",
            "employment_type": "FULL_TIME",
        },
        "location": {
            "city": "Barcelona",
            "country_code": "ES",
            "country_name": "Spain",
        },
        "contract": {"term_type": "FIXED_TERM"},
        "description": {
            "full_jd": (
                f"{title}. Research role involving exercise, physical activity, health, cognition, "
                "human intervention research and data analysis. A relevant PhD is required."
            ),
            "detail_status": "FULL",
        },
        "requirements": {},
        "raw_extra": {
            "state_event": {"seen_status": "SEEN"},
            "evaluation": {"recommendation": "REVIEW"},
        },
        "lifecycle_status": "OPEN",
    }


def full_record(job_id: str, origin: str, decision: str, confidence: int = 88) -> FullEvaluationRecord:
    return FullEvaluationRecord(
        job_id=job_id,
        origin=origin,
        triage_id=f"triage-{job_id}" if origin == ORIGIN_LLM_RESCUE else None,
        evaluation={
            "cache_hit": False,
            "llm_result": {
                "decision": decision,
                "confidence": confidence,
                "reason_short": f"LLM says {decision} for {job_id}.",
            },
        },
    )


class LLMShadowExcelL72Tests(unittest.TestCase):
    def test_main_preserves_every_main_job_even_without_llm_result(self):
        jobs = [
            canonical("main-evaluated", "Postdoctoral Fellow in Exercise Neuroscience"),
            canonical("main-missing", "Research Fellow in Health"),
        ]
        rows = build_llm_shadow_report_rows(
            jobs,
            main_job_ids={"main-evaluated", "main-missing"},
            full_evaluation_records=[
                full_record("main-evaluated", ORIGIN_MAIN, "APPLY"),
            ],
        )
        by_title = {row["title"]: row for row in rows.main}
        self.assertEqual(len(rows.main), 2)
        self.assertEqual(
            by_title["Research Fellow in Health"]["llm_evaluation"],
            "NOT_EVALUATED",
        )
        self.assertEqual(
            by_title["Research Fellow in Health"]["agreement"],
            "NO_LLM_RESULT",
        )

    def test_llm_rescued_contains_only_favorable_rescue_full_evaluations(self):
        jobs = [
            canonical("rescue-apply", "Research Fellow in Behavioral Medicine"),
            canonical("rescue-review", "Postdoc in Rehabilitation"),
            canonical("rescue-skip", "Research Fellow in Automotive Radar"),
        ]
        rows = build_llm_shadow_report_rows(
            jobs,
            main_job_ids=set(),
            full_evaluation_records=[
                full_record("rescue-apply", ORIGIN_LLM_RESCUE, "APPLY"),
                full_record("rescue-review", ORIGIN_LLM_RESCUE, "REVIEW"),
                full_record("rescue-skip", ORIGIN_LLM_RESCUE, "SKIP"),
            ],
        )
        decisions = {row["llm_evaluation"] for row in rows.llm_rescued}
        titles = {row["title"] for row in rows.llm_rescued}
        self.assertTrue(decisions.issubset(FAVORABLE_LLM_DECISIONS))
        self.assertEqual(
            titles,
            {"Research Fellow in Behavioral Medicine", "Postdoc in Rehabilitation"},
        )

    def test_disagreements_contains_main_only_not_rescue_duplicates(self):
        jobs = [
            canonical("main", "Postdoctoral Fellow in Exercise Neuroscience"),
            canonical("rescue", "Research Fellow in Behavioral Medicine"),
        ]
        baseline = build_llm_shadow_report_rows(
            jobs,
            main_job_ids={"main"},
            full_evaluation_records=[],
        )
        rule = baseline.main[0]["rule_evaluation"]
        llm_opposite = "SKIP" if rule != "SKIP" else "STRONG_APPLY"

        rows = build_llm_shadow_report_rows(
            jobs,
            main_job_ids={"main"},
            full_evaluation_records=[
                full_record("main", ORIGIN_MAIN, llm_opposite),
                full_record("rescue", ORIGIN_LLM_RESCUE, "APPLY"),
            ],
        )
        self.assertEqual(len(rows.disagreements), 1)
        self.assertEqual(rows.disagreements[0]["title"], "Postdoctoral Fellow in Exercise Neuroscience")
        self.assertNotEqual(rows.disagreements[0]["rule_evaluation"], rows.disagreements[0]["llm_evaluation"])

    def test_report_builder_does_not_mutate_canonical_jobs(self):
        jobs = [canonical("main", "Postdoctoral Fellow in Exercise Neuroscience")]
        before = copy.deepcopy(jobs)
        build_llm_shadow_report_rows(
            jobs,
            main_job_ids={"main"},
            full_evaluation_records=[full_record("main", ORIGIN_MAIN, "APPLY")],
        )
        self.assertEqual(jobs, before)

    def test_workbook_has_only_agreed_three_llm_sheets_and_expected_columns(self):
        jobs = [
            canonical("main", "Postdoctoral Fellow in Exercise Neuroscience"),
            canonical("rescue", "Research Fellow in Behavioral Medicine"),
        ]
        baseline = build_llm_shadow_report_rows(jobs, main_job_ids={"main"}, full_evaluation_records=[])
        rule = baseline.main[0]["rule_evaluation"]
        llm_opposite = "SKIP" if rule != "SKIP" else "STRONG_APPLY"

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "llm-shadow.xlsx"
            build_llm_shadow_xlsx(
                jobs,
                output,
                main_job_ids={"main"},
                full_evaluation_records=[
                    full_record("main", ORIGIN_MAIN, llm_opposite),
                    full_record("rescue", ORIGIN_LLM_RESCUE, "APPLY"),
                ],
            )

            with zipfile.ZipFile(output) as z:
                ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                wb = ET.fromstring(z.read("xl/workbook.xml"))
                names = [s.attrib["name"] for s in wb.findall("m:sheets/m:sheet", ns)]
                self.assertEqual(names, ["MAIN", "LLM_RESCUED", "DISAGREEMENTS"])
                self.assertNotIn("REVIEW_MORE", names)

                shared = z.read("xl/sharedStrings.xml").decode("utf-8")
                self.assertIn(">Rule Evaluation<", shared)
                self.assertIn(">LLM Evaluation<", shared)
                self.assertIn(">Agreement<", shared)
                self.assertIn(">LLM Reason<", shared)


if __name__ == "__main__":
    unittest.main()
