from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.llm.context_quality import clean_vacancy_text, extract_sections, prepare_vacancy_context
from src.llm.shadow_evaluator import build_llm_input

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "config" / "llm_candidate_profile_v1.json").read_text(encoding="utf-8"))


def canonical_job(full_jd: str) -> dict:
    return {
        "source_record_id": "l3:test",
        "canonical_id": "l3-canonical",
        "source": {"detail_url": "https://example.org/jobs/l3"},
        "position": {
            "title_raw": "Research Fellow",
            "institution_raw": "Example University",
            "role_level": "POSTDOC",
            "employment_type": "FULL_TIME",
        },
        "location": {"city": "Barcelona", "country_code": "ES", "country_name": "Spain"},
        "contract": {"term_type": "FIXED_TERM"},
        "description": {"full_jd": full_jd, "detail_status": "FULL"},
        "requirements": {},
        "raw_extra": {},
        "classification": {"pre_evaluation_disposition": "SKIP"},
    }


class LLMContextQualityL3Tests(unittest.TestCase):
    def test_cleanup_removes_only_clear_ui_boilerplate_and_exact_duplicate_blocks(self):
        text = (
            "Skip to main content\n\n"
            "Research Fellow in Stress Biology\n\n"
            "The project studies exercise, stress and cognition in adults.\n\n"
            "The project studies exercise, stress and cognition in adults.\n\n"
            "Apply now\n"
        )
        cleaned, boilerplate_removed, duplicates_removed = clean_vacancy_text(text)
        self.assertNotIn("Skip to main content", cleaned)
        self.assertNotIn("Apply now", cleaned)
        self.assertEqual(cleaned.count("The project studies exercise, stress and cognition in adults."), 1)
        self.assertEqual(boilerplate_removed, 2)
        self.assertEqual(duplicates_removed, 1)

    def test_section_extraction_uses_source_headings_and_preserves_content(self):
        text = (
            "Research Fellow\n\n"
            "Key Responsibilities\n"
            "Run human intervention visits.\n"
            "Analyse physiological data.\n\n"
            "Essential Criteria\n"
            "PhD in a relevant discipline.\n"
            "Experience with human research.\n\n"
            "Desirable Criteria\n"
            "Experience with neuroimaging.\n"
        )
        cleaned, _, _ = clean_vacancy_text(text)
        sections = extract_sections(cleaned)
        self.assertIn("Run human intervention visits.", sections["responsibilities"])
        self.assertIn("PhD in a relevant discipline.", sections["essential"])
        self.assertIn("Experience with neuroimaging.", sections["desirable"])

    def test_non_target_heading_stops_section_capture(self):
        text = (
            "Essential Criteria\n"
            "PhD in a relevant discipline.\n\n"
            "Benefits\n"
            "Private health insurance and pension contribution.\n"
        )
        cleaned, _, _ = clean_vacancy_text(text)
        sections = extract_sections(cleaned)
        self.assertIn("PhD in a relevant discipline.", sections["essential"])
        self.assertNotIn("Private health insurance", sections["essential"])

    def test_no_truncation_when_under_soft_budget(self):
        text = "Role overview\n\nEssential Criteria\nPhD required."
        context = prepare_vacancy_context(text, max_chars=10_000)
        self.assertFalse(context.truncated)
        self.assertEqual(context.full_text, context.full_text.strip())
        self.assertNotIn("omitted because context budget", context.full_text)

    def test_long_context_preserves_essential_desirable_and_responsibility_sections(self):
        filler = ("General institutional information and project background. " * 300)
        text = (
            filler
            + "\n\nKey Responsibilities\nRun the randomized human intervention and physiological assessments.\n"
            + "\nEssential Criteria\nA PhD in exercise physiology, neuroscience, psychology, or a related field is mandatory.\n"
            + "\nDesirable Criteria\nNeuroimaging exposure is desirable but not essential.\n\n"
            + filler
        )
        context = prepare_vacancy_context(text, max_chars=5_000)
        self.assertTrue(context.truncated)
        self.assertIn("Run the randomized human intervention", context.full_text)
        self.assertIn("A PhD in exercise physiology", context.full_text)
        self.assertIn("Neuroimaging exposure is desirable but not essential", context.full_text)
        self.assertEqual(context.truncation_strategy, "SECTION_PRESERVING_HEAD_TAIL")

    def test_protected_sections_may_exceed_soft_budget_instead_of_being_silently_cut(self):
        essential = "Mandatory evidence sentence. " * 220
        text = f"Essential Criteria\n{essential}\n\nDesirable Criteria\nUseful but optional experience."
        context = prepare_vacancy_context(text, max_chars=4_000)
        self.assertIn("Mandatory evidence sentence.", context.full_text)
        self.assertGreater(len(context.full_text), 4_000)
        self.assertEqual(context.truncation_strategy, "PROTECTED_SECTIONS_ONLY_OVER_SOFT_BUDGET")

    def test_build_llm_input_populates_sections_without_rule_output_leakage(self):
        text = (
            "Research Fellow\n\nResponsibilities\nConduct stress and exercise experiments.\n\n"
            "Essential Requirements\nPhD in a relevant field.\n\n"
            "Preferred Qualifications\nExperience with MRI is preferred."
        )
        payload = build_llm_input(canonical_job(text), PROFILE)
        self.assertIn("Conduct stress and exercise experiments", payload["job"]["responsibilities_text"])
        self.assertIn("PhD in a relevant field", payload["job"]["essential_criteria_text"])
        self.assertIn("Experience with MRI is preferred", payload["job"]["desirable_criteria_text"])
        serialized = json.dumps(payload)
        self.assertNotIn("pre_evaluation_disposition", serialized)
        self.assertNotIn('"SKIP"', serialized)

    def test_explicit_source_sections_take_precedence_over_extracted_sections(self):
        job = canonical_job("Essential Criteria\nExtracted criterion from full JD.")
        job["requirements"]["essential_criteria_text"] = "Explicit source-derived essential criterion."
        payload = build_llm_input(job, PROFILE)
        self.assertEqual(payload["job"]["essential_criteria_text"], "Explicit source-derived essential criterion.")


if __name__ == "__main__":
    unittest.main()
