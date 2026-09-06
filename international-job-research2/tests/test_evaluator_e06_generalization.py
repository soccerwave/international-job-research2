from __future__ import annotations

import unittest

from src.evaluation.calibrated_e06 import evaluate_calibrated


def vacancy(*, title: str, jd: str, role: str = "POSTDOC", recommendation: str = "REVIEW", scientific: str = "ADJACENT", blockers=None, reviews=None, country: str = "GB"):
    return {
        "canonical_id": "synthetic",
        "position": {"title_raw": title, "role_family": role},
        "location": {"country_code": country, "country_name": country},
        "dates": {},
        "source": {"retrieved_at": "2026-09-05T00:00:00+00:00", "source_key": "test"},
        "description": {"detail_status": "FULL", "full_jd": jd},
        "requirements": {},
        "raw_extra": {"evaluation": {
            "evaluator_version": "E0.1",
            "recommendation": recommendation,
            "pre_evaluation_disposition": "POLICY_REVIEW",
            "role_family": role,
            "role_policy_status": "PRIMARY",
            "dimensions": {"scientific": scientific, "level": "STRONG", "methods": "UNKNOWN", "language": "CLEAR", "mobility": "POTENTIALLY_VIABLE", "registration": "CLEAR", "contract": "UNKNOWN"},
            "review_codes": list(reviews or []),
            "blocker_codes": list(blockers or []),
            "evidence": {},
            "reason": "baseline"
        }}
    }


class E06GeneralizationTests(unittest.TestCase):
    def test_direct_exercise_does_not_override_australia_work_rights_blocker(self):
        x = vacancy(
            title="Associate Lecturer/Lecturer - Exercise Physiology",
            country="AU",
            jd="Exercise Science and Exercise Physiology. Visa sponsorship is not available. Candidates must hold unrestricted work rights to be considered."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_relevant_neuroscience_does_not_override_mandatory_german_and_neuroimaging(self):
        x = vacancy(
            title="University Assistant postdoctoral",
            country="AT",
            jd="Environmental neuroscience, stress and resilience research. Neuroimaging expertise is mandatory. Excellent German C1 and English are mandatory for teaching and clinical collaboration."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_senior_lecturer_is_outside_target_stage(self):
        x = vacancy(
            title="Senior Lecturer Medical Education",
            role="LECTURER",
            jd="Lead medical education curriculum, placement education and accreditation."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_explicit_business_faculty_title_is_discipline_mismatch(self):
        x = vacancy(
            title="Assistant Professor BSc Business and Management",
            role="ASSISTANT_PROFESSOR",
            jd="Teach business strategy, management and entrepreneurship in higher education."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_central_bayesian_cognitive_modelling_is_specialist_mismatch(self):
        x = vacancy(
            title="Postdoc Position: A Model-Based Approach to Understanding Cognitive Development",
            jd="Develop Bayesian cognitive models of infant learning. You have experience with advanced computational modelling techniques and a PhD in cognitive science, developmental cognitive neuroscience or AI."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_human_randomized_trial_with_psychosocial_outcomes_is_reviewable(self):
        x = vacancy(
            title="Post-Doctoral Research Associate - Trial Manager",
            recommendation="SKIP",
            scientific="UNCLEAR",
            jd="Manage a definitive cluster randomised controlled trial in young adults with diabetes. The intervention targets self-management and psychosocial outcomes and is led with a Professor of Health Psychology."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_epidemiology_with_optional_genomics_is_reviewable_not_omics_skip(self):
        x = vacancy(
            title="Postdoctoral Research Associate in Epidemiology and Health Data Science",
            jd="Analyse longitudinal health data, frailty and diabetes using R and epidemiological methods. Experience of genomic data or polygenic risk scores would be advantageous. The project brings together epidemiology, healthy ageing, genomics and population health."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_integrative_microbiome_brain_body_role_is_reviewable_without_mandatory_specialist_method(self):
        x = vacancy(
            title="Post-Doctoral Researcher (Integrative Biologist) - Microbiome Centre",
            recommendation="SKIP",
            scientific="ADJACENT",
            jd="Study microbiome and host-microbe biology across systems physiology, endocrine signalling, psychosocial stress, brain function and behaviour. Broad experience in systems physiology, metabolomics and/or endocrine biology is welcomed."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_integrative_biology_with_mandatory_wet_lab_method_stays_skip(self):
        x = vacancy(
            title="Post-Doctoral Researcher (Integrative Biologist)",
            jd="Study microbiome, brain function, endocrine signalling and behaviour. Hands-on experience in cell culture and mass spectrometry is required and essential for the role."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_direct_sport_science_with_niche_high_altitude_mri_expertise_is_review(self):
        x = vacancy(
            title="Universitätsassistent:in - Postdoc",
            recommendation="REVIEW",
            scientific="UNCLEAR",
            country="AT",
            jd="Department of Sport Science. Research and teaching in performance physiology. Expertise in environmental physiology with a particular focus on high-altitude physiology and magnetic resonance imaging is required."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_stress_wearable_postdoc_remains_surfaced(self):
        x = vacancy(
            title="Postdoctoral Researcher Stress in Action",
            recommendation="APPLY",
            scientific="STRONG",
            country="NL",
            jd="Study daily-life stress using wearables, ecological momentary assessment, psychological and physiological measures and multimodal health data."
        )
        self.assertIn(evaluate_calibrated(x)["recommendation"], {"STRONG_APPLY", "APPLY", "REVIEW"})

    def test_clear_sport_medicine_exercise_physiology_postdoc_remains_strong_or_apply(self):
        x = vacancy(
            title="University Assistant postdoctoral",
            recommendation="APPLY",
            scientific="STRONG",
            country="AT",
            jd="Centre for Sport Science. Department Sports Medicine, Exercise Physiology and Prevention. Conduct exercise physiology research and physiological testing. German is desirable but not mandatory."
        )
        self.assertIn(evaluate_calibrated(x)["recommendation"], {"STRONG_APPLY", "APPLY"})


if __name__ == "__main__":
    unittest.main()
