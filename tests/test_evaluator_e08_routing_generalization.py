from __future__ import annotations

import unittest

from src.evaluation.calibrated_e08 import evaluate_calibrated


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


class E08RoutingGeneralizationTests(unittest.TestCase):
    def test_relevant_open_topic_w1_is_review_not_hidden(self) -> None:
        result = evaluate_calibrated(
            job(
                title="W1-Junior Professorship with Tenure Track - Open Topic",
                country="DE",
                text=(
                    "The Faculty of Medicine seeks an open-topic W1 junior professor. "
                    "The Faculty's key research areas are ageing, neurosciences, oncology and trauma. "
                    "Applicants require a doctoral degree, teaching aptitude and an independent research profile."
                ),
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["operational_route"], "JOBS")

    def test_open_topic_engineering_is_not_rescued(self) -> None:
        result = evaluate_calibrated(
            job(
                title="W1 Junior Professorship with Tenure Track - Open Topic",
                country="DE",
                text=(
                    "The Faculty of Engineering invites applications. The strategic research areas are robotics, "
                    "autonomous systems, control engineering and smart manufacturing. A doctorate is required."
                ),
            )
        )
        self.assertNotEqual(result["operational_route"], "JOBS")

    def test_external_pdf_does_not_rescue_timber_engineering_postdoc(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Postdoctoral Researcher - Timber Systems",
                text=(
                    "The School of Engineering and Timber Engineering Research Group studies structural timber, "
                    "glulam connections, wood rheology and building systems. Please review the full job description "
                    "for further details and essential requirements."
                ),
            )
        )
        self.assertEqual(result["operational_route"], "HIDDEN")
        self.assertFalse(result["needs_detail_review"])

    def test_external_pdf_does_not_rescue_device_engineering_postdoc(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Post-Doctoral Research Associate - Medical Device Development",
                text=(
                    "The School of Engineering medical-device laboratory develops diagnostic and therapeutic devices, "
                    "stents and commercial medtech prototypes. Please review the full job description for further "
                    "details and essential requirements."
                ),
            )
        )
        self.assertEqual(result["operational_route"], "HIDDEN")
        self.assertFalse(result["needs_detail_review"])

    def test_direct_exercise_science_is_not_suppressed_by_engineering_context(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Postdoctoral Researcher in Exercise Physiology",
                text=(
                    "Based in a School of Engineering collaboration, this role studies exercise physiology, physical "
                    "activity and human performance using wearable sensors. Please review the full job description "
                    "for further details and essential requirements."
                ),
            )
        )
        self.assertTrue(result["needs_detail_review"])
        self.assertEqual(result["operational_route"], "NEEDS_DETAIL_REVIEW")

    def test_candidate_information_package_with_selection_criteria_is_detail_review(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Post-Doctoral Researcher - Integrative Brain-Body Biology",
                text=(
                    "The project examines microbiome, endocrine, neural and behavioural systems under psychosocial stress. "
                    "For an information package including full details of the post, selection criteria and application "
                    "process see the recruitment portal."
                ),
            )
        )
        self.assertTrue(result["needs_detail_review"])
        self.assertEqual(result["operational_route"], "NEEDS_DETAIL_REVIEW")

    def test_candidate_pack_does_not_override_explicit_student_role(self) -> None:
        result = evaluate_calibrated(
            job(
                title="PhD Student in Neuroscience",
                text=(
                    "For a candidate information package including full details, selection criteria and application "
                    "process see the recruitment portal."
                ),
            )
        )
        self.assertFalse(result["needs_detail_review"])
        self.assertEqual(result["operational_route"], "HIDDEN")

    def test_generic_technology_word_does_not_create_unrelated_domain_hard_skip(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Postdoctoral Researcher in Digital Health",
                text=(
                    "The health technology project studies physical activity, behavioural medicine and digital health. "
                    "Full selection criteria are available in the linked candidate brief document."
                ),
            )
        )
        self.assertTrue(result["needs_detail_review"])
        self.assertEqual(result["operational_route"], "NEEDS_DETAIL_REVIEW")

    def test_candidate_pack_does_not_rescue_unrelated_mathematics_lecturer(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Lecturer in Mathematics",
                text=(
                    "The School of Mathematical Sciences seeks a lecturer in pure and applied mathematics. "
                    "For an information package including full details of the post, selection criteria and application "
                    "process see the recruitment portal."
                ),
            )
        )
        self.assertFalse(result["needs_detail_review"])
        self.assertEqual(result["operational_route"], "HIDDEN")

    def test_candidate_pack_does_not_override_mandatory_professional_registration(self) -> None:
        result = evaluate_calibrated(
            job(
                title="Lecturer in Social Work",
                text=(
                    "Applicants must be eligible for mandatory CORU professional registration as a social worker. "
                    "For an information package including full details of the post, selection criteria and application "
                    "process see the recruitment portal."
                ),
            )
        )
        self.assertFalse(result["needs_detail_review"])
        self.assertEqual(result["operational_route"], "HIDDEN")


if __name__ == "__main__":
    unittest.main()
