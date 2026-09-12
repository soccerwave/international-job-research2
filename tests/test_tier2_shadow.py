import unittest

from src.evaluation.tier2_shadow import evaluate_tier2_shadow


def job(title: str) -> dict:
    return {"position": {"title_raw": title}}


class Tier2ShadowTests(unittest.TestCase):
    def test_generic_data_and_analytics_are_shadow_candidates(self):
        for title in [
            "Data Analyst",
            "BI Analyst",
            "Business Analyst",
            "Data Scientist",
            "Analytics Engineer",
        ]:
            with self.subTest(title=title):
                self.assertTrue(evaluate_tier2_shadow(job(title))["would_skip"])

    def test_training_roles_are_shadow_candidates(self):
        for title in [
            "Consulting Trainer",
            "Technical Trainer",
            "Formateur Habilitations Electriques",
            "Ausbilder Technik",
        ]:
            with self.subTest(title=title):
                self.assertTrue(evaluate_tier2_shadow(job(title))["would_skip"])

    def test_generic_engineering_roles_are_shadow_candidates(self):
        for title in [
            "Simulation Engineer",
            "Systems Engineer",
            "Mechanical Engineer",
            "Ingenieur Systeme",
            "Ingegnere di processo",
        ]:
            with self.subTest(title=title):
                self.assertTrue(evaluate_tier2_shadow(job(title))["would_skip"])

    def test_research_and_academic_identity_protects_overlap(self):
        for title in [
            "Research Engineer in Neuroimaging",
            "Postdoctoral Data Scientist in Digital Health",
            "Research Scientist in Health Data Science",
            "Researcher in Business Analytics and Population Health",
        ]:
            with self.subTest(title=title):
                result = evaluate_tier2_shadow(job(title))
                self.assertTrue(result["matched"] or "research scientist" in title.lower() or "researcher" in title.lower())
                self.assertTrue(result["protected"])
                self.assertFalse(result["would_skip"])

    def test_unrelated_research_identity_is_still_protected_in_shadow(self):
        result = evaluate_tier2_shadow(job("Research Engineer in Power Systems"))
        self.assertTrue(result["matched"])
        self.assertTrue(result["protected"])
        self.assertFalse(result["would_skip"])

    def test_unmatched_title_is_unchanged(self):
        result = evaluate_tier2_shadow(job("Research Fellow in Exercise Physiology"))
        self.assertFalse(result["matched"])
        self.assertFalse(result["would_skip"])


if __name__ == "__main__":
    unittest.main()
