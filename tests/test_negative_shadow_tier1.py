import unittest

from src.evaluation.negative_shadow_tier1 import evaluate_negative_shadow


def job(title: str) -> dict:
    return {"position": {"title_raw": title}}


class Tier1NegativeShadowTests(unittest.TestCase):
    def test_financial_stress_testing_is_shadow_skip(self):
        result = evaluate_negative_shadow(job("Business Analyst - Credit Risk Stress Testing"))
        self.assertTrue(result["would_skip"])
        self.assertEqual(result["matched_rules"][0]["rule_id"], "FINANCE_BANKING_RISK_T1")

    def test_school_teacher_multilingual_is_shadow_skip(self):
        for title in [
            "Nauczyciel matematyki",
            "Professeur particulier de mathématiques",
            "Lehrer Mathematik",
            "Profesor particular de inglés",
        ]:
            with self.subTest(title=title):
                self.assertTrue(evaluate_negative_shadow(job(title))["would_skip"])

    def test_clinical_practitioner_multilingual_is_shadow_skip(self):
        for title in ["Assistenzarzt Neurologie", "Facharzt Psychiatrie", "Médecin généraliste"]:
            with self.subTest(title=title):
                self.assertTrue(evaluate_negative_shadow(job(title))["would_skip"])

    def test_target_academic_title_protects_candidate(self):
        result = evaluate_negative_shadow(job("Postdoctoral Research Fellow in Credit Risk Stress Testing"))
        self.assertTrue(result["matched"])
        self.assertTrue(result["protected"])
        self.assertFalse(result["would_skip"])
        self.assertEqual(result["protection_reason"], "TARGET_ACADEMIC_TITLE")

    def test_direct_profile_title_protects_candidate(self):
        result = evaluate_negative_shadow(job("Administrator - Physical Activity Research"))
        self.assertTrue(result["matched"])
        self.assertTrue(result["protected"])
        self.assertFalse(result["would_skip"])
        self.assertEqual(result["protection_reason"], "DIRECT_PROFILE_TITLE")

    def test_unmatched_title_is_unchanged_shadow(self):
        result = evaluate_negative_shadow(job("Research Fellow in Exercise Physiology"))
        self.assertFalse(result["matched"])
        self.assertFalse(result["would_skip"])


if __name__ == "__main__":
    unittest.main()
