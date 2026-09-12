import unittest

from src.evaluation.tier2_shadow import evaluate_tier2_shadow
from scripts.build_user_excel import apply_tier1_report_filter


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
        for title in [
            "Research Engineer in Power Systems",
            "Principal Research Software Engineer",
            "Senior Research Data Engineer",
            "Ingénieur de recherche Stress abiotique des plantes F/H",
            "Ingegnere di ricerca in sistemi embedded",
            "Ingeniero de investigacion en sistemas",
            "Forschungsingenieur Robotik",
            "Scientific Software Engineer",
        ]:
            with self.subTest(title=title):
                result = evaluate_tier2_shadow(job(title))
                self.assertTrue(result["matched"] or "scientific software engineer" in title.lower())
                self.assertTrue(result["protected"])
                self.assertFalse(result["would_skip"])

    def test_unmatched_title_is_unchanged(self):
        result = evaluate_tier2_shadow(job("Research Fellow in Exercise Physiology"))
        self.assertFalse(result["matched"])
        self.assertFalse(result["would_skip"])

    def test_safe_subsets_are_filterable_but_riskier_subsets_remain_shadow_only(self):
        safe_titles = [
            "Business Intelligence Analyst",
            "Business Analyst",
            "Reporting Analyst",
            "Consulting Trainer",
            "Formateur Habilitations Electriques",
            "Mechanical Engineer",
            "Civil Engineer",
            "Process Engineer",
        ]
        shadow_titles = [
            "Data Scientist",
            "Data Analyst",
            "Data Engineer",
            "Analytics Engineer",
            "Software Engineer",
            "Systems Engineer",
            "Simulation Engineer",
            "Ingenieur Systeme",
        ]
        for title in safe_titles:
            with self.subTest(title=title, mode="safe"):
                result = evaluate_tier2_shadow(job(title))
                self.assertTrue(result["would_filter"])
                self.assertFalse(result["protected"])
        for title in shadow_titles:
            with self.subTest(title=title, mode="shadow"):
                result = evaluate_tier2_shadow(job(title))
                self.assertFalse(result["would_filter"])
                self.assertTrue(result["shadow_only_candidate"])

    def test_multilingual_research_identities_protect_overlap(self):
        titles = [
            "Chercheur Data Scientist en santé numérique",
            "Investigadora Data Analyst en salud pública",
            "Ricercatore Data Engineer in neuroscienze",
            "Onderzoeker Systems Engineer Neuroimaging",
            "Wissenschaftliche Mitarbeiterin Software Engineer",
        ]
        for title in titles:
            with self.subTest(title=title):
                result = evaluate_tier2_shadow(job(title))
                self.assertTrue(result["protected"])
                self.assertFalse(result["would_filter"])
                self.assertFalse(result["would_skip"])

    def test_user_report_removes_safe_subsets_and_retains_shadow_candidates(self):
        titles = [
            "Business Analyst",
            "Consulting Trainer",
            "Mechanical Engineer",
            "Data Scientist",
            "Software Engineer",
            "Simulation Engineer",
            "Postdoctoral Business Analyst in Population Health",
        ]
        kept = apply_tier1_report_filter([job(title) for title in titles])
        self.assertEqual(
            [item["position"]["title_raw"] for item in kept],
            [
                "Data Scientist",
                "Software Engineer",
                "Simulation Engineer",
                "Postdoctoral Business Analyst in Population Health",
            ],
        )


if __name__ == "__main__":
    unittest.main()
