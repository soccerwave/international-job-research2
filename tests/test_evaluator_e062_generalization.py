from __future__ import annotations

import unittest

from src.evaluation.calibrated_e062 import evaluate_calibrated
from tests.test_evaluator_e06_generalization import vacancy


class E062GeneralizationTests(unittest.TestCase):
    def test_german_c2_desirable_is_not_a_hard_blocker(self):
        x = vacancy(
            title="Universitätsassistent*in Postdoc",
            recommendation="STRONG_APPLY",
            scientific="STRONG",
            country="AT",
            jd=(
                "Department of Sport Medicine, Exercise Physiology and Prevention. "
                "Conduct performance physiology research and teaching. "
                "Wünschenswert sind Kenntnisse in Deutsch auf dem Level C2 und Englisch auf dem Level C1."
            ),
        )
        self.assertIn(evaluate_calibrated(x)["recommendation"], {"STRONG_APPLY", "APPLY"})

    def test_german_c1_mandatory_remains_skip(self):
        x = vacancy(
            title="University Assistant postdoctoral",
            recommendation="APPLY",
            scientific="STRONG",
            country="AT",
            jd="Exercise neuroscience research. German C1 is mandatory for teaching and clinical collaboration.",
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_generic_phd_or_industrial_experience_does_not_bind_later_management_word(self):
        x = vacancy(
            title="Research Fellow in Portfolio Impact Assessment",
            recommendation="REVIEW",
            scientific="ADJACENT",
            country="GB",
            jd=(
                "Coordinate a portfolio of funded research projects, grant reporting and external partnerships. "
                "You should have: A PhD or significant practical/industrial experience. "
                "Significant industrial experience demonstrating research and management excellence. "
                "Experience contributing to research funding proposals is essential."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_explicit_phd_in_management_remains_skip(self):
        x = vacancy(
            title="Research Fellow",
            recommendation="REVIEW",
            scientific="ADJACENT",
            country="GB",
            jd="Applicants must hold a PhD in management or business and demonstrate an established management research programme.",
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_existing_e061_immunologist_blocker_remains_skip(self):
        x = vacancy(
            title="Post-Doctoral Researcher (Immunologist) - Microbiome Centre",
            recommendation="SKIP",
            scientific="ADJACENT",
            country="IE",
            jd="The microbiome-gut-brain project requires deep expertise in experimental immunology and immune cell phenotyping.",
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_existing_e061_optional_genomics_rescue_remains_review(self):
        x = vacancy(
            title="Postdoctoral Research Associate in Epidemiology and Health Data Science",
            recommendation="SKIP",
            scientific="ADJACENT",
            blockers=["MANDATORY_SPECIALIST_OMICS_GENOMICS_E05"],
            jd=(
                "Analyse longitudinal health data using epidemiological methods and R. "
                "Experience of genomic data or polygenic risk scores would be advantageous."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
