import copy
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from tests.test_user_excel import record
from src.reporting.user_excel import build_review_rows, build_user_rows, build_user_xlsx
from scripts.build_user_excel import build_user_summary


class ReviewMoreTests(unittest.TestCase):
    def test_operational_titles_never_enter_either_sheet(self):
        titles = ["Catering Van Driver", "IT Security Lead", "Systems Administrator",
                  "Education Partnerships Officer", "HDR Engagement Manager",
                  "Information Security Specialist", "Social Media Lead",
                  "Student Conduct Investigator", "Student Cultural Wellbeing Officer",
                  "Operational Support Officer", "Senior Network Administrator"]
        for title in titles:
            for status, text in [("FULL", "Physical activity and mental health benefits. " * 20),
                                 ("UNAVAILABLE", "")]:
                with self.subTest(title=title, status=status):
                    job = record(priority="APPLY", title=title, full_jd=text)
                    job["description"]["detail_status"] = status
                    before = copy.deepcopy(job)
                    self.assertEqual(build_user_rows([job]), [])
                    self.assertEqual(build_review_rows([job]), [])
                    self.assertEqual(job, before)

    def test_generic_research_and_research_on_drivers_are_preserved(self):
        for title in ["Research Fellow", "Postdoctoral Research Fellow",
                      "Lecturer in Exercise Science",
                      "Postdoc studying stress in bus drivers",
                      "Research Fellow in information security and mental health"]:
            with self.subTest(title=title):
                job = record(priority="APPLY", title=title)
                self.assertTrue(build_user_rows([job]))
                job["description"] = {"detail_status": "UNAVAILABLE", "full_jd": ""}
                self.assertTrue(build_user_rows([job]) or build_review_rows([job]))

    def test_union_preserves_jobs_and_exports_disjoint_review_types(self):
        jobs = record(priority="APPLY", title="Postdoc Exercise Physiology")
        rescue = record(priority="SKIP", title="Generic fellowship", full_jd="Unclassified subject. " * 30)
        detail = record(priority="SKIP", title="Generic research position", full_jd="Unclassified subject. " * 30)
        closed = record(priority="SKIP", title="Closed role", lifecycle="CLOSED", full_jd="Unclassified subject. " * 30)
        hidden = record(priority="SKIP", title="Other role", full_jd="Unclassified subject. " * 30)
        seen_again = record(priority="SKIP", title="Seen rescue", full_jd="Unclassified subject. " * 30)
        rescue["raw_extra"]["state"]["seen_status"] = "NEW"
        detail["raw_extra"]["state"]["seen_status"] = "MATERIALLY_CHANGED"
        closed["raw_extra"]["state"]["seen_status"] = "NEW"
        hidden["raw_extra"]["state"]["seen_status"] = "NEW"
        seen_again["raw_extra"]["state"]["seen_status"] = "SEEN"
        records = [jobs, rescue, detail, closed, hidden, seen_again]
        before = copy.deepcopy(records)
        baseline = build_user_rows(records)
        self.assertEqual([r["title"] for r in baseline], [jobs["position"]["title_raw"]])
        def route(r):
            return {"operational_route": {
                "Generic fellowship": "JOBS", "Generic research position": "NEEDS_DETAIL_REVIEW",
                "Closed role": "JOBS", "Other role": "HIDDEN", "Seen rescue": "JOBS",
            }.get(r["position"]["title_raw"], "HIDDEN")}
        with patch("src.reporting.user_excel.evaluate_recall_first_e11", side_effect=route):
            rows = build_review_rows(records)
            self.assertEqual({r["review_type"] for r in rows}, {"RESCUE_REVIEW", "NEEDS_DETAIL_REVIEW"})
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["seen_status"] for r in rows}, {"NEW", "MATERIALLY_CHANGED"})
            self.assertNotIn("Seen rescue", {r["title"] for r in rows})
            self.assertFalse({r["title"] for r in baseline} & {r["title"] for r in rows})
            summary = build_user_summary(records, {"run_id": "test"})
            self.assertEqual(summary["review_more_count"], 2)
            self.assertEqual(summary["total_visible"], 3)
            with tempfile.TemporaryDirectory() as d:
                output = Path(d) / "report.xlsx"
                build_user_xlsx(iter(records), output)
                with zipfile.ZipFile(output) as z:
                    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                    wb = ET.fromstring(z.read("xl/workbook.xml"))
                    self.assertEqual([s.attrib["name"] for s in wb.findall("m:sheets/m:sheet", ns)], ["JOBS", "REVIEW_MORE"])
                    for number, count in [(1, 2), (2, 3)]:
                        sheet = ET.fromstring(z.read(f"xl/worksheets/sheet{number}.xml"))
                        self.assertEqual(len(sheet.findall("m:sheetData/m:row", ns)), count)
                        self.assertIsNotNone(sheet.find("m:autoFilter", ns))
                        self.assertEqual(len(sheet.findall("m:hyperlinks/m:hyperlink", ns)), count - 1)
        self.assertEqual(records, before)


if __name__ == "__main__":
    unittest.main()
