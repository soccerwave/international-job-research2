from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from src.reporting.user_excel import USER_COLUMNS, build_user_rows, build_user_xlsx


def record(
    *,
    priority: str,
    title: str,
    deadline: str = "",
    deadline_text: str = "",
    lifecycle: str = "OPEN",
    country: str = "Spain",
    role: str = "POSTDOC",
    institution: str = "Example University",
    institution_normalized: str = "",
    city: str = "Barcelona",
    url: str = "https://example.com/job",
    full_jd: str = "Physical activity intervention and exercise physiology research.",
    level: str | None = None,
):
    if level is None:
        level = "STRONG" if role in {"POSTDOC", "RESEARCH_FELLOW_POSTDOC"} else "ACCEPTABLE"
    return {
        "canonical_id": title,
        "source_record_id": title,
        "source": {"apply_url": url, "provider": "test", "source_status": lifecycle},
        "position": {
            "title_raw": title,
            "institution_raw": institution,
            "institution_normalized": institution_normalized or None,
            "role_family": role,
        },
        "location": {"country_name": country, "city": city or None},
        "dates": {"deadline_at": deadline or None, "deadline_text": deadline_text or None},
        "description": {"detail_status": "FULL", "full_jd": full_jd},
        "raw_extra": {
            "state": {"lifecycle_status": lifecycle},
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": priority,
                "pre_evaluation_disposition": "ELIGIBLE_FOR_EVALUATION",
                "role_family": role,
                "role_policy_status": "PRIMARY" if role in {"POSTDOC", "RESEARCH_FELLOW_POSTDOC", "LECTURER", "ASSISTANT_PROFESSOR"} else "AMBIGUOUS",
                "dimensions": {
                    "scientific": "GOOD",
                    "level": level,
                    "methods": "UNKNOWN",
                    "language": "CLEAR",
                    "mobility": "POTENTIALLY_VIABLE",
                    "registration": "CLEAR",
                    "contract": "UNKNOWN",
                },
                "fit_signals": [],
                "review_codes": [],
                "blocker_codes": [],
                "evidence": {},
                "reason": "test baseline",
            },
        },
    }


class UserExcelTests(unittest.TestCase):
    def test_rows_are_actionable_only_and_sorted_strong_apply_review_then_deadline(self):
        rows = build_user_rows(
            [
                record(priority="REVIEW", title="Research Fellow in Digital Health and Rehabilitation", deadline="2026-09-09T00:00:00+00:00", full_jd="Digital health, rehabilitation, wearables and behaviour change."),
                record(priority="APPLY", title="Later apply", deadline="2026-10-01T00:00:00+00:00", full_jd="Physical activity research."),
                record(priority="STRONG_APPLY", title="Strong job", full_jd="Exercise physiology and human movement research."),
                record(priority="LOW_PRIORITY", title="Low job", full_jd="Algebraic graph theory research with a complete detailed description that has no health, exercise, stress or neuroscience relevance at all. " * 4),
                record(priority="APPLY", title="Sooner apply", deadline="2026-09-15T00:00:00+00:00", full_jd="Physical activity research."),
                record(priority="SKIP", title="Postdoc in International Law", full_jd="Legal research and teaching."),
                record(priority="REVIEW", title="Closed review", lifecycle="CLOSED", full_jd="Digital health and rehabilitation research."),
            ]
        )
        self.assertEqual(
            [(row["recommendation"], row["title"]) for row in rows],
            [
                ("STRONG_APPLY", "Strong job"),
                ("APPLY", "Sooner apply"),
                ("APPLY", "Later apply"),
                ("REVIEW", "Research Fellow in Digital Health and Rehabilitation"),
            ],
        )
        self.assertEqual(rows[1]["deadline"], "2026-09-15")
        self.assertNotIn("LOW_PRIORITY", [row["recommendation"] for row in rows])
        self.assertNotIn("SKIP", [row["recommendation"] for row in rows])

    def test_presentation_cleans_euraxess_institution_city_and_deadline(self):
        noisy_institution = (
            "s Initiatives Science4Refugees ERA4Ukraine Network EURAXESS National Portals "
            "EURAXESS Network Map EURAXESS Worldwide EURAXESS Support Centres ERA Talent Platform "
            "Home Jobs & Opportunities Job offer JOB Netherlands Delft University of Technology"
        )
        rows = build_user_rows(
            [
                record(
                    priority="APPLY",
                    title="Postdoc Physical Activity Intervention",
                    country="Netherlands",
                    institution=noisy_institution,
                    city="",
                    deadline_text=(
                        "1 Oct 2026 - 21:59 (UTC) Country Netherlands Type of Contract Temporary "
                        "Job Status Full-time"
                    ),
                    full_jd=(
                        "Physical activity intervention research. Job Information Organisation/Company "
                        "Delft University of Technology (TU Delft) Research Field Health Researcher Profile "
                        "Recognised Researcher (R2) Application Deadline 1 Oct 2026 - 21:59 (UTC) Country Netherlands. "
                        "Work Location(s) Number of offers available 1 Company/Institute Delft University "
                        "of Technology Country Netherlands City Delft Contact Website https://www.tudelft.nl/"
                    ),
                )
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["institution"], "Delft University of Technology (TU Delft)")
        self.assertEqual(rows[0]["city"], "Delft")
        self.assertEqual(rows[0]["deadline"], "2026-10-01")
        self.assertNotIn("EURAXESS", rows[0]["institution"])

    def test_deadline_parser_handles_ordinal_and_numeric_portal_text(self):
        rows = build_user_rows(
            [
                record(
                    priority="APPLY",
                    title="Postdoc Physical Activity Ordinal date",
                    deadline_text="Sunday, 27th September 2026 Additional Information",
                    full_jd="Physical activity research.",
                ),
                record(
                    priority="APPLY",
                    title="Postdoc Physical Activity Numeric date",
                    deadline_text="12:00 noon (local Irish time) on 16/9/2026 Applications must be submitted",
                    full_jd="Physical activity research.",
                ),
            ]
        )
        by_title = {row["title"]: row for row in rows}
        self.assertEqual(by_title["Postdoc Physical Activity Ordinal date"]["deadline"], "2026-09-27")
        self.assertEqual(by_title["Postdoc Physical Activity Numeric date"]["deadline"], "2026-09-16")

    def test_excel_has_two_sheets_and_unchanged_jobs_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "international_academic_job_report.xlsx"
            build_user_xlsx(
                [record(priority="STRONG_APPLY", title="Strong job", full_jd="Exercise physiology and human movement research.")],
                output,
            )
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1000)
            with zipfile.ZipFile(output) as archive:
                workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
                shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
            self.assertIn('name="JOBS"', workbook_xml)
            self.assertIn('name="REVIEW_MORE"', workbook_xml)
            for _key, label, _width in USER_COLUMNS:
                self.assertIn(f">{label}<", shared_strings)
            self.assertNotIn(">Evaluator reason<", shared_strings)
            self.assertNotIn(">State event<", shared_strings)
            self.assertEqual(len(USER_COLUMNS), 8)


if __name__ == "__main__":
    unittest.main()

