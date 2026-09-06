from __future__ import annotations

import unittest

from src.evaluation.calibrated_e061 import evaluate_calibrated
from tests.test_evaluator_e06_generalization import vacancy


class E061GeneralizationTests(unittest.TestCase):
    def test_specialist_immunologist_is_not_rescued_by_microbiome_brain_adjacency(self):
        x = vacancy(
            title="Post-Doctoral Researcher (Immunologist) - Microbiome Centre",
            recommendation="SKIP",
            scientific="ADJACENT",
            country="IE",
            jd=(
                "The microbiome-gut-brain programme studies brain and behavioural function. "
                "The successful candidate will bring deep expertise in experimental immunology. "
                "The work includes immune cell phenotyping, myeloid populations, cytokine signalling, "
                "microglial activation and neuroimmune communication."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_broad_integrative_biologist_can_still_surface(self):
        x = vacancy(
            title="Post-Doctoral Researcher (Integrative Biologist) - Microbiome Centre",
            recommendation="SKIP",
            scientific="ADJACENT",
            country="IE",
            jd=(
                "Study microbiome and host-microbe biology across systems physiology, endocrine signalling, "
                "psychosocial stress, brain function and behaviour. Broad experience in systems physiology, "
                "metabolomics and/or endocrine biology is welcomed."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_epidemiology_optional_genomics_surfaces_for_review(self):
        x = vacancy(
            title="Postdoctoral Research Associate in Epidemiology and Health Data Science",
            recommendation="SKIP",
            scientific="ADJACENT",
            blockers=["MANDATORY_SPECIALIST_OMICS_GENOMICS_E05"],
            jd=(
                "Analyse longitudinal electronic health records, frailty and diabetes using R and epidemiological methods. "
                "Experience of linked NHS data, longitudinal modelling, frailty, diabetes, genomic data or polygenic risk "
                "scores would be advantageous. The project includes genomic data but the central role is epidemiology."
            ),
        )
        out = evaluate_calibrated(x)
        self.assertEqual(out["recommendation"], "REVIEW")
        self.assertNotIn("MANDATORY_SPECIALIST_OMICS_GENOMICS_E05", out.get("blocker_codes", []))

    def test_optional_omics_rule_does_not_override_unrelated_hard_blocker(self):
        x = vacancy(
            title="Postdoctoral Research Associate in Epidemiology and Health Data Science",
            recommendation="SKIP",
            blockers=["MANDATORY_SPECIALIST_OMICS_GENOMICS_E05", "MANDATORY_ADVANCED_AI_ML"],
            jd=(
                "Analyse longitudinal health data. Experience of genomic data would be advantageous. "
                "Advanced machine learning research expertise is mandatory and central to this role."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_australia_explicit_work_rights_blocker_remains_skip(self):
        x = vacancy(
            title="Associate Lecturer/Lecturer - Exercise Physiology",
            country="AU",
            jd="Exercise Physiology. Visa sponsorship is not available. Candidates must hold unrestricted Australian work rights.",
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_core_stress_wearable_role_remains_surfaced(self):
        x = vacancy(
            title="Postdoctoral Researcher Stress in Action",
            recommendation="APPLY",
            scientific="STRONG",
            country="NL",
            jd="Study daily-life stress using wearables, EMA, psychological and physiological measures and multimodal health data.",
        )
        self.assertIn(evaluate_calibrated(x)["recommendation"], {"STRONG_APPLY", "APPLY", "REVIEW"})


if __name__ == "__main__":
    unittest.main()
