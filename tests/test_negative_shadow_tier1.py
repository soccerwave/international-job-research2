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
        for title in [
            "Assistenzarzt Neurologie",
            "Assistenzärztin Neurologie",
            "Facharzt Psychiatrie",
            "Fachärztin Psychiatrie",
            "Médecin généraliste",
        ]:
            with self.subTest(title=title):
                self.assertTrue(evaluate_negative_shadow(job(title))["would_skip"])

    def test_target_academic_title_protects_candidate(self):
        result = evaluate_negative_shadow(job("Postdoctoral Research Fellow in Credit Risk Stress Testing"))
        self.assertTrue(result["matched"])
        self.assertTrue(result["protected"])
        self.assertFalse(result["would_skip"])
        self.assertEqual(result["protection_reason"], "TARGET_ACADEMIC_TITLE")

    def test_thematic_profile_phrase_does_not_protect_non_target_occupation(self):
        result = evaluate_negative_shadow(job("Administrator - Physical Activity Research"))
        self.assertTrue(result["matched"])
        self.assertFalse(result["protected"])
        self.assertTrue(result["would_skip"])

    def test_rehabilitation_does_not_protect_physician_identity(self):
        result = evaluate_negative_shadow(job("Assistenzarzt Geriatrie in der Rehabilitation"))
        self.assertTrue(result["matched"])
        self.assertFalse(result["protected"])
        self.assertTrue(result["would_skip"])

    def test_medical_adjective_alone_is_not_practitioner_identity(self):
        result = evaluate_negative_shadow(job("Investigador Coordinador en Biotecnologia Medica"))
        self.assertFalse(result["matched"])
        self.assertFalse(result["would_skip"])

    def test_unmatched_title_is_unchanged_shadow(self):
        result = evaluate_negative_shadow(job("Research Fellow in Exercise Physiology"))
        self.assertFalse(result["matched"])
        self.assertFalse(result["would_skip"])


if __name__ == "__main__":
    unittest.main()
