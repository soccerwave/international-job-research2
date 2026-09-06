from __future__ import annotations

import unittest

from src.evaluation.calibrated_e041 import evaluate_calibrated


def vacancy(*, title: str, jd: str, recommendation: str = "REVIEW", scientific: str = "UNCLEAR") -> dict:
    return {
        "canonical_id": "synthetic",
        "position": {"title_raw": title, "role_family": "POSTDOC"},
        "location": {"country_code": "BE", "country_name": "Belgium"},
        "dates": {},
        "source": {"retrieved_at": "2026-09-05T00:00:00+00:00", "source_key": "test"},
        "description": {"detail_status": "FULL", "full_jd": jd},
        "requirements": {},
        "raw_extra": {
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": recommendation,
                "pre_evaluation_disposition": "POLICY_REVIEW",
                "role_family": "POSTDOC",
                "role_policy_status": "PRIMARY",
                "dimensions": {
                    "scientific": scientific,
                    "level": "STRONG",
                    "methods": "UNKNOWN",
                    "language": "CLEAR",
                    "mobility": "POTENTIALLY_VIABLE",
                    "registration": "CLEAR",
                    "contract": "UNKNOWN"
                },
                "review_codes": ["UNCLEAR_DOMAIN"] if scientific == "UNCLEAR" else [],
                "blocker_codes": [],
                "evidence": {},
                "reason": "baseline"
            }
        }
    }


class E041BoilerplateTests(unittest.TestCase):
    def test_rehabilitation_act_in_equal_opportunity_text_is_not_scientific_fit(self):
        x = vacancy(
            title="Postdoctoral Scientist in Multimodal Representation Learning for Predictive Biology",
            jd=(
                "Postdoctoral scientist in advanced AI/ML modelling, deep learning, computer vision and multi-omics for drug discovery. "
                "PhD in Computer Science, Electrical Engineering or Applied Mathematics. Strong AI/ML publication record required. "
                "The employer is an Equal Opportunity Employer. Applicants with disabilities are protected under Section 503 of the Rehabilitation Act."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_real_rehabilitation_science_before_boilerplate_remains_actionable(self):
        x = vacancy(
            title="Postdoctoral Researcher in Rehabilitation",
            jd=(
                "Research project in rehabilitation, physical activity and recovery after illness. PhD in a health-related discipline required. "
                "The employer is an Equal Opportunity Employer and provides reasonable accommodation."
            ),
            scientific="ADJACENT",
        )
        self.assertIn(evaluate_calibrated(x)["recommendation"], {"STRONG_APPLY", "APPLY", "REVIEW"})

    def test_title_adjacent_signal_is_not_removed_by_boilerplate_filter(self):
        x = vacancy(
            title="Postdoctoral Researcher in Digital Health",
            jd=(
                "Develop and evaluate digital interventions in healthcare. PhD in a health-related discipline. "
                "Equal Opportunity Employer. Reasonable accommodation is available."
            ),
            scientific="ADJACENT",
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
