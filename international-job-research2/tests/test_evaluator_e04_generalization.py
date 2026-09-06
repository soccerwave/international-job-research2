from __future__ import annotations

import unittest

from src.evaluation.calibrated_e04 import evaluate_calibrated


def job(*, title: str, jd: str, role: str = "POSTDOC", recommendation: str = "REVIEW", scientific: str = "ADJACENT", blockers=None):
    role_status = "PRIMARY" if role in {"POSTDOC", "LECTURER", "ASSISTANT_PROFESSOR", "RESEARCH_FELLOW_POSTDOC"} else "AMBIGUOUS"
    return {
        "canonical_id": "synthetic",
        "position": {"title_raw": title, "role_family": role},
        "location": {"country_code": "GB", "country_name": "United Kingdom"},
        "dates": {},
        "source": {"retrieved_at": "2026-09-05T00:00:00+00:00", "source_key": "test"},
        "description": {"detail_status": "FULL", "full_jd": jd},
        "requirements": {},
        "raw_extra": {
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": recommendation,
                "pre_evaluation_disposition": "POLICY_REVIEW",
                "role_family": role,
                "role_policy_status": role_status,
                "dimensions": {
                    "scientific": scientific,
                    "level": "STRONG" if role == "POSTDOC" else "ACCEPTABLE",
                    "methods": "UNKNOWN",
                    "language": "CLEAR",
                    "mobility": "POTENTIALLY_VIABLE",
                    "registration": "CLEAR",
                    "contract": "UNKNOWN"
                },
                "review_codes": [],
                "blocker_codes": list(blockers or []),
                "evidence": {},
                "reason": "baseline"
            }
        }
    }


class E04GeneralizationTests(unittest.TestCase):
    def test_direct_exercise_postdoc_can_remain_strong(self):
        x = job(
            title="Postdoctoral Researcher in Exercise Physiology",
            recommendation="STRONG_APPLY",
            scientific="STRONG",
            jd="Postdoctoral research in exercise physiology and sports medicine. PhD in Exercise Physiology or Sport Science. Quantitative research experience required."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "STRONG_APPLY")

    def test_expired_relevant_job_is_skip(self):
        x = job(
            title="Postdoctoral Researcher in Stress Biology",
            recommendation="APPLY",
            scientific="STRONG",
            jd="Stress biology and cortisol research. Application deadline: 18 June 2026. PhD required."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_developmental_psychology_faculty_is_discipline_mismatch(self):
        x = job(
            title="Assistant Professor in Developmental Psychology",
            role="ASSISTANT_PROFESSOR",
            jd="School of Psychology seeks an Assistant Professor in Developmental Psychology. PhD in Psychology required. Research and teaching in developmental psychology."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_computational_neuroscience_required_specialism_is_skip(self):
        x = job(
            title="Postdoctoral Fellow in Computational Neuroscience",
            jd="Neuroscience postdoc. Applicants must have advanced signal processing and detailed biophysical modelling experience for high-density neural recordings."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_brain_ageing_required_bioinformatics_is_skip(self):
        x = job(
            title="Postdoctoral Fellow in Brain Aging",
            jd="Brain ageing project. Strong background in bioinformatics, genomics and transcriptomics is required for analysis of high-throughput sequencing data."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_neurodegeneration_required_disease_models_is_skip(self):
        x = job(
            title="Postdoctoral Research Fellow - Parkinson's",
            jd="Neuroscience research. Proven experience in neurodegenerative disorders using rodent models and stereotaxic methods is required."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_preferred_molecular_methods_do_not_create_hard_blocker(self):
        x = job(
            title="Translational Scientist - Schizophrenia",
            role="RESEARCH_SCIENTIST",
            jd="Neural-circuit and schizophrenia research. PhD in neuroscience or related field required. Molecular biology, ASO biochemistry and two-photon imaging experience are preferred, not required."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_law_faculty_is_skip_despite_cognition_word(self):
        x = job(
            title="Lecturer in International Law",
            role="LECTURER",
            jd="Lecturer in International Law. Teaching legal doctrine and research. The university supports cognition and wellbeing initiatives. PhD in Law required."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_generic_research_title_without_profile_anchor_does_not_pollute_review(self):
        x = job(
            title="Research Fellow",
            role="OTHER_RESEARCH",
            jd="Research Fellow in an interdisciplinary institute. Applicants should have a PhD and strong research experience. Project details are provided after shortlisting."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_preferred_computational_methods_in_adjacent_neuroscience_remain_review(self):
        x = job(
            title="Postdoc in Connectomics",
            jd="Connectomics and neuroscience project. A PhD in neuroscience or related discipline is required. Computational modelling and wet-lab methods are desirable and preferred."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_protected_identity_restriction_is_review_when_scientifically_relevant(self):
        x = job(
            title="Research Fellow in Urban Health",
            role="RESEARCH_FELLOW_POSTDOC",
            jd="Urban health research fellowship. This identified position is open to Aboriginal and Torres Strait Islander candidates only. PhD in public health or related field required."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_phd_student_role_is_skip(self):
        x = job(title="PhD Researcher in Exercise Science", role="UNKNOWN", jd="PhD researcher position in exercise science and physical activity.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")


if __name__ == "__main__":
    unittest.main()
