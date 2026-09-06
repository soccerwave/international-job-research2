from __future__ import annotations

import unittest

from src.evaluation.calibrated_e07 import evaluate_calibrated


def job(*, title: str, text: str, detail_status: str = "FULL", country: str = "IE") -> dict:
    return {
        "canonical_id": "synthetic",
        "position": {
            "title_raw": title,
            "role_family": "UNKNOWN",
            "role_level": "UNKNOWN",
            "institution_raw": "Test University",
        },
        "location": {"country_code": country, "country_name": "Test"},
        "description": {
            "detail_status": detail_status,
            "full_jd": text,
            "detail_failure_reason": None,
        },
        "requirements": {
            "degree_fields": [],
            "degree_text": None,
            "language_requirements": [],
            "methods_preferred": [],
            "methods_required": [],
            "phd_requirement": "UNKNOWN",
            "professional_registration_text": None,
            "sponsorship_text": None,
            "teaching_requirement_text": None,
            "work_rights_text": None,
            "years_postdoc": None,
        },
        "classification": {
            "blocker_codes": [],
            "review_codes": [],
            "pre_evaluation_disposition": "ELIGIBLE_FOR_EVALUATION",
            "role_policy_status": "AMBIGUOUS",
            "market_tier": "CORE",
        },
        "source": {"source_key": "synthetic", "provider": "synthetic"},
        "raw_extra": {},
    }


class E07DetailRoutingTests(unittest.TestCase):
    def test_postdoc_wrapper_with_external_essential_requirements_is_detail_review(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Post-Doctoral Research Associate",
                text=(
                    "Applications are invited for a postdoctoral role in an interdisciplinary health technology lab. "
                    "Please review full job description for further details and essential requirements. "
                    "Full Job Description.pdf"
                ),
            )
        )
        self.assertTrue(result["needs_detail_review"])
        self.assertTrue(result["operational_surface"])
        self.assertEqual(result["operational_route"], "NEEDS_DETAIL_REVIEW")

    def test_research_fellow_wrapper_with_external_selection_criteria_is_detail_review(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Research Fellow - Evidence Synthesis",
                text=(
                    "The centre conducts health research methodology, evidence synthesis and randomised trials. "
                    "Essential criteria are provided in the linked role profile document."
                ),
            )
        )
        self.assertTrue(result["needs_detail_review"])
        self.assertTrue(result["operational_surface"])

    def test_fetch_failed_plausible_postdoc_fails_open_to_detail_review(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Postdoctoral Researcher in Health Behaviour",
                text="",
                detail_status="FETCH_FAILED",
            )
        )
        self.assertTrue(result["needs_detail_review"])
        self.assertTrue(result["operational_surface"])

    def test_fetch_failed_explicit_phd_position_does_not_pollute_detail_queue(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Fully Funded PhD Positions in Molecular Physics",
                text="",
                detail_status="FETCH_FAILED",
            )
        )
        self.assertFalse(result["needs_detail_review"])
        self.assertFalse(result["operational_surface"])

    def test_partial_student_assistant_does_not_pollute_detail_queue(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Studentische Mitarbeit in Forschung und Verwaltung",
                text="Student assistant role in atmospheric science.",
                detail_status="PARTIAL",
                country="AT",
            )
        )
        self.assertFalse(result["needs_detail_review"])
        self.assertFalse(result["operational_surface"])

    def test_complete_unrelated_postdoc_is_not_saved_by_detail_channel(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Postdoctoral Researcher in Polymer Chemistry",
                text="A complete advert requiring a PhD in polymer chemistry and specialist synthetic chemistry expertise.",
                detail_status="FULL",
            )
        )
        self.assertFalse(result["needs_detail_review"])

    def test_complete_direct_exercise_role_stays_in_jobs_route(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Postdoctoral Researcher in Exercise Physiology",
                text=(
                    "Research in exercise physiology, physical activity and human performance. "
                    "Applicants should hold a relevant PhD."
                ),
                detail_status="FULL",
            )
        )
        self.assertFalse(result["needs_detail_review"])
        if result["recommendation"] in {"STRONG_APPLY", "APPLY", "REVIEW"}:
            self.assertEqual(result["operational_route"], "JOBS")

    def test_secondary_non_enabled_admin_title_is_not_detail_review_merely_because_research_is_mentioned(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Clinical Trials Officer",
                text=(
                    "Administrative officer supporting investigators with regulatory, ethics, legal, data protection, "
                    "pre-award and post-award processes for clinical trials. Full advert provided here."
                ),
                detail_status="FULL",
            )
        )
        self.assertFalse(result["needs_detail_review"])


if __name__ == "__main__":
    unittest.main()
