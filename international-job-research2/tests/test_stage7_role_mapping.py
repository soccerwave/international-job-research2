import unittest

from tests.test_stage7_evaluator import base_job
from src.evaluation import evaluate_vacancy


class Stage7RoleMappingTests(unittest.TestCase):
    def test_research_project_manager_is_secondary_review(self):
        job = base_job(
            title="Research Project Manager in Physical Activity and Health",
            jd="Manage a multidisciplinary physical activity and health research project, coordinate partners, support grant reporting and scientific delivery.",
        )
        result = evaluate_vacancy(job)
        self.assertEqual(result["role_family"], "RESEARCH_PROJECT_MANAGER")
        self.assertEqual(result["role_policy_status"], "SECONDARY")
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertIn("SECONDARY_ROLE_DISABLED_BY_DEFAULT", result["review_codes"])

    def test_scientific_project_manager_is_secondary_review(self):
        job = base_job(
            title="Scientific Project Manager - Neuroscience and Stress Research",
            jd="Coordinate an international neuroscience and stress research programme, scientific reporting, consortium management and grant delivery.",
        )
        result = evaluate_vacancy(job)
        self.assertEqual(result["role_family"], "SCIENTIFIC_PROJECT_MANAGER")
        self.assertEqual(result["role_policy_status"], "SECONDARY")
        self.assertEqual(result["recommendation"], "REVIEW")

    def test_research_programme_manager_is_secondary_review(self):
        job = base_job(
            title="Research Programme Manager - Brain Health",
            jd="Programme management for brain health and cognitive neuroscience research, including grant coordination and partner management.",
        )
        result = evaluate_vacancy(job)
        self.assertEqual(result["role_family"], "RESEARCH_PROGRAMME_MANAGER")
        self.assertEqual(result["role_policy_status"], "SECONDARY")
        self.assertEqual(result["recommendation"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
