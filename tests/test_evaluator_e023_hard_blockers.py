from __future__ import annotations

import unittest

from src.evaluation.calibrated_e021 import evaluate_calibrated


def vacancy(*, title: str, jd: str, country: str = "GB", role: str = "POSTDOC"):
    return {
        "position": {"title_raw": title, "role_family": role},
        "location": {"country_code": country},
        "description": {"detail_status": "FULL", "full_jd": jd},
        "requirements": {},
        "raw_extra": {
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": "APPLY",
                "pre_evaluation_disposition": "ELIGIBLE_FOR_EVALUATION",
                "role_family": role,
                "role_policy_status": "PRIMARY",
                "dimensions": {
                    "scientific": "GOOD",
                    "level": "STRONG",
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
                "reason": "baseline",
            }
        },
    }


class ConservativeHardBlockerTests(unittest.TestCase):
    def test_equine_veterinary_clinical_identity_is_skip(self):
        result = evaluate_calibrated(
            vacancy(
                title="The Ella McGregor Senior Lecturer / Lecturer in Equine Sport Medicine",
                role="LECTURER",
                jd=(
                    "We seek an experienced equine clinician to join the veterinary school sports medicine service. "
                    "The role includes lameness diagnostics, referral-level clinical cases and on-call clinical work."
                ),
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("EQUINE_VETERINARY_CLINICAL_IDENTITY_E023", result["blocker_codes"])

    def test_human_sports_medicine_is_not_equine_blocked(self):
        result = evaluate_calibrated(
            vacancy(
                title="Lecturer in Sports Medicine and Exercise Physiology",
                role="LECTURER",
                jd=(
                    "Teaching and research in human sports medicine, exercise physiology, physical activity and athlete health. "
                    "The post includes supervision of student research and human exercise testing."
                ),
            )
        )
        self.assertNotIn("EQUINE_VETERINARY_CLINICAL_IDENTITY_E023", result.get("blocker_codes", []))

    def test_equine_research_without_clinical_service_is_not_hard_blocked(self):
        result = evaluate_calibrated(
            vacancy(
                title="Postdoctoral Researcher in Equine Exercise Physiology",
                jd=(
                    "Research on equine exercise physiology and comparative responses to training. "
                    "The project is research-focused and does not include veterinary referral practice or clinical service."
                ),
            )
        )
        self.assertNotIn("EQUINE_VETERINARY_CLINICAL_IDENTITY_E023", result.get("blocker_codes", []))

    def test_australia_no_sponsorship_and_full_rights_to_work_is_skip(self):
        result = evaluate_calibrated(
            vacancy(
                title="Post-Doctoral Fellow (Exercise Physiology)",
                country="AU",
                jd=(
                    "Visa sponsorship is not available for this position. Applicants must have full rights to work in Australia. "
                    "The research program focuses on exercise physiology and human performance."
                ),
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED_E023", result["blocker_codes"])

    def test_australia_no_sponsorship_without_explicit_rights_requirement_is_not_hard_blocked(self):
        result = evaluate_calibrated(
            vacancy(
                title="Post-Doctoral Fellow in Exercise Science",
                country="AU",
                jd=(
                    "Visa sponsorship is not available. The project focuses on exercise science and physical activity. "
                    "Applicants should review the university employment conditions before applying."
                ),
            )
        )
        self.assertNotIn("AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED_E023", result.get("blocker_codes", []))

    def test_australia_preferred_work_rights_is_not_hard_blocked(self):
        result = evaluate_calibrated(
            vacancy(
                title="Postdoctoral Research Fellow in Physical Activity",
                country="AU",
                jd=(
                    "Visa sponsorship is not available. Candidates with full rights to work in Australia are preferred, "
                    "but eligibility will be reviewed individually. The role studies physical activity interventions."
                ),
            )
        )
        self.assertNotIn("AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED_E023", result.get("blocker_codes", []))


if __name__ == "__main__":
    unittest.main()
