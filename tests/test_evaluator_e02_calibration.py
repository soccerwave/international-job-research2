from __future__ import annotations

import unittest

from src.evaluation.calibrated_e02 import evaluate_calibrated


def vacancy(*, title: str, jd: str, role: str, level: str = "STRONG", mobility: str = "POTENTIALLY_VIABLE"):
    return {
        "position": {"title_raw": title, "role_family": role},
        "description": {"detail_status": "FULL", "full_jd": jd},
        "requirements": {},
        "raw_extra": {
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": "APPLY",
                "pre_evaluation_disposition": "ELIGIBLE_FOR_EVALUATION",
                "role_family": role,
                "role_policy_status": "PRIMARY" if role in {"POSTDOC", "LECTURER", "ASSISTANT_PROFESSOR", "RESEARCH_FELLOW_POSTDOC"} else "AMBIGUOUS",
                "dimensions": {
                    "scientific": "GOOD",
                    "level": level,
                    "methods": "UNKNOWN",
                    "language": "CLEAR",
                    "mobility": mobility,
                    "registration": "CLEAR",
                    "contract": "UNKNOWN",
                },
                "fit_signals": [],
                "review_codes": [],
                "blocker_codes": [],
                "evidence": {},
                "reason": "baseline",
            }
        },
    }


class CalibratedEvaluatorTests(unittest.TestCase):
    def test_recognition_does_not_match_cognition(self):
        job = vacancy(
            title="Lecturer in International Law",
            role="LECTURER",
            level="ACCEPTABLE",
            jd="The school seeks legal research and teaching. Recognition of teaching excellence is valued.",
        )
        result = evaluate_calibrated(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertEqual(result["dimensions"]["scientific"], "WEAK")

    def test_generic_training_does_not_create_exercise_fit(self):
        job = vacancy(
            title="PostDoc in Multilayer Meta-Optics for High-Performance Optical Systems",
            role="POSTDOC",
            jd="The project covers photonics and optical systems. High-quality researcher training is provided.",
        )
        result = evaluate_calibrated(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertNotIn("training", " ".join(result.get("fit_signals") or []).lower())

    def test_generic_fitness_benefit_does_not_create_scientific_fit(self):
        job = vacancy(
            title="Business Manager",
            role="UNKNOWN",
            level="UNKNOWN",
            jd="Manage budgets, operations and contracts. Staff receive fitness benefits and wellbeing discounts.",
        )
        result = evaluate_calibrated(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertNotIn("fitness", " ".join(result.get("fit_signals") or []).lower())

    def test_sport_and_exercise_facility_boilerplate_does_not_create_fit(self):
        job = vacancy(
            title="Postdoctoral Researcher in Archaeology",
            role="POSTDOC",
            jd="Archaeological research and material culture. Employees may use campus sport and exercise facilities.",
        )
        result = evaluate_calibrated(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertEqual(result["dimensions"]["scientific"], "WEAK")

    def test_exercise_postdoc_remains_strong_apply(self):
        job = vacancy(
            title="University Assistant postdoctoral",
            role="POSTDOC",
            jd="Institute for Sports and Human Movement Science. Research in exercise physiology and sports medicine.",
        )
        result = evaluate_calibrated(job)
        self.assertEqual(result["recommendation"], "STRONG_APPLY")
        self.assertEqual(result["dimensions"]["scientific"], "STRONG")

    def test_pure_cognitive_development_is_review_not_strong(self):
        job = vacancy(
            title="Postdoc Position in Cognitive Development in Early Childhood",
            role="POSTDOC",
            jd="Research focuses on cognitive neuroscience and cognition in early childhood with computational modelling.",
        )
        result = evaluate_calibrated(job)
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["dimensions"]["scientific"], "ADJACENT")

    def test_digital_health_rehabilitation_is_review(self):
        job = vacancy(
            title="Research Fellow – Digital Health & Rehabilitation",
            role="RESEARCH_FELLOW_POSTDOC",
            jd="Digital health, rehabilitation, wearables and behaviour change are central to the project.",
        )
        result = evaluate_calibrated(job)
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["dimensions"]["scientific"], "ADJACENT")

    def test_phd_position_is_explicitly_out_of_scope(self):
        job = vacancy(
            title="PhD position in IC Design group",
            role="UNKNOWN",
            level="UNKNOWN",
            jd="Doctoral training position in integrated circuit design.",
        )
        result = evaluate_calibrated(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("ROLE_STUDENT_E02", result["blocker_codes"])

    def test_hyphenated_postdoctoral_title_is_not_misclassified_as_student(self):
        job = vacancy(
            title="Post-Doctoral Researcher (Systems Neuroscientist)",
            role="OUT_OF_SCOPE",
            level="MISMATCH",
            jd="Systems neuroscience research on brain circuits and behaviour.",
        )
        job["raw_extra"]["evaluation"]["role_policy_status"] = "OUT_OF_SCOPE"
        job["raw_extra"]["evaluation"]["blocker_codes"] = ["ROLE_STUDENT"]
        result = evaluate_calibrated(job)
        self.assertEqual(result["role_family"], "POSTDOC")
        self.assertEqual(result["role_policy_status"], "PRIMARY")
        self.assertNotIn("ROLE_STUDENT", result["blocker_codes"])
        self.assertEqual(result["recommendation"], "REVIEW")

    def test_coru_requirement_blocks_social_care_role(self):
        job = vacancy(
            title="Lecturer in Social Care",
            role="LECTURER",
            level="ACCEPTABLE",
            jd="Applicants must be registered with CORU or be eligible for CORU registration.",
        )
        result = evaluate_calibrated(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("MANDATORY_CORU_REGISTRATION_E02", result["blocker_codes"])

    def test_primary_role_without_relevant_anchor_downgrades_to_low_priority(self):
        job = vacancy(
            title="Postdoctoral Researcher - Data Engineering",
            role="POSTDOC",
            jd="Research on data engineering, distributed systems and digital trust.",
        )
        result = evaluate_calibrated(job)
        self.assertIn(result["recommendation"], {"SKIP", "LOW_PRIORITY"})
        self.assertNotEqual(result["recommendation"], "APPLY")


if __name__ == "__main__":
    unittest.main()
