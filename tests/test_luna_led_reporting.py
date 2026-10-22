from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from src.llm.full_evaluation_routing import FullEvaluationRecord, ORIGIN_MAIN, ORIGIN_LLM_RESCUE
from src.reporting.luna_led_excel import build_luna_led_rows, build_luna_led_xlsx
def canonical(job_id, title):
    return {
        "canonical_id": job_id,
        "source": {"listing_url": f"https://example.org/{job_id}"},
        "position": {"title_raw": title, "institution_raw": "Example University",
                     "role_level": "POSTDOC", "employment_type": "FULL_TIME"},
        "location": {"city": "Barcelona", "country_code": "ES", "country_name": "Spain"},
        "contract": {"term_type": "FIXED_TERM"},
        "description": {"full_jd": "Research exercise health relevant PhD",
                        "detail_status": "FULL"},
        "requirements": {},
        "raw_extra": {"state_event": {"seen_status": "SEEN"},
                      "evaluation": {"recommendation": "REVIEW"}},
        "lifecycle_status": "OPEN",
    }


def full_record(job_id, origin, decision):
    return FullEvaluationRecord(
        job_id=job_id, origin=origin, triage_id=None,
        evaluation={"llm_result": {"decision": decision, "confidence": 85,
                                   "reason_short": f"Reason for {job_id}"}},
    )


class LunaLedReportingTests(unittest.TestCase):
    def setUp(self):
        self.jobs = [canonical(k, k) for k in (
            "main-apply", "main-skip", "main-missing", "rescue-strong",
            "rescue-review", "rescue-skip", "both",
        )]
        self.records = [
            full_record("main-apply", ORIGIN_MAIN, "APPLY"),
            full_record("main-skip", ORIGIN_MAIN, "SKIP"),
            full_record("rescue-strong", ORIGIN_LLM_RESCUE, "STRONG_APPLY"),
            full_record("rescue-review", ORIGIN_LLM_RESCUE, "REVIEW"),
            full_record("rescue-skip", ORIGIN_LLM_RESCUE, "SKIP"),
            full_record("both", ORIGIN_MAIN, "REVIEW"),
            full_record("both", ORIGIN_LLM_RESCUE, "STRONG_APPLY"),
        ]
        self.ids = {"main-apply", "main-skip", "main-missing", "both"}

    def test_union_provenance_priority_and_no_duplicates(self):
        r = build_luna_led_rows(self.jobs, main_job_ids=self.ids, full_evaluation_records=self.records)
        self.assertEqual([x["title"] for x in r["MAIN"]],
                         ["rescue-strong", "main-apply", "both", "rescue-review"])
        self.assertEqual([x["source_path"] for x in r["MAIN"]],
                         ["RESCUE", "MAIN", "MAIN", "RESCUE"])
        self.assertEqual([x["title"] for x in r["SKIPPED"]], ["main-skip", "rescue-skip"])
        self.assertEqual([x["title"] for x in r["NO_LLM_RESULT"]], ["main-missing"])
        self.assertEqual(len({x["title"] for x in r["MAIN"]}), len(r["MAIN"]))
        self.assertTrue(all(x["rule_evaluation"] for x in r["MAIN"]))

    def test_xlsx_layout_and_no_mutation(self):
        import copy
        before = copy.deepcopy(self.jobs)
        with tempfile.TemporaryDirectory() as tmp:
            path = build_luna_led_xlsx(self.jobs, Path(tmp) / "report.xlsx",
                    main_job_ids=self.ids, full_evaluation_records=self.records)
            with zipfile.ZipFile(path) as f:
                xml = ET.fromstring(f.read("xl/workbook.xml"))
                ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                names = [s.attrib["name"] for s in xml.findall(".//x:sheet", ns)]
                self.assertEqual(names, ["MAIN", "SKIPPED", "NO_LLM_RESULT", "DISAGREEMENTS"])
                shared = f.read("xl/sharedStrings.xml").decode()
                self.assertIn("Source Path", shared)
                self.assertIn("Luna Decision", shared)
        self.assertEqual(self.jobs, before)


if __name__ == "__main__":
    unittest.main()
