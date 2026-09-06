from __future__ import annotations

import unittest

from src.evaluation.calibrated_e021 import evaluate_calibrated


def vacancy(*, title: str, jd: str, role: str = "POSTDOC", level: str = "STRONG"):
    return {
        "position": {"title_raw": title, "role_family": role},
        "description": {"detail_status": "FULL", "full_jd": jd},
        "requirements": {},
        "raw_extra": {
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": "APPLY",
                "pre_evaluation_disposition": "ELIGIBLE_FOR_EVALUATION",
                "role_family": role,
                "role_policy_status": "PRIMARY" if role in {"POSTDOC", "LECTURER", "ASSISTANT_PROFESSOR", "RESEARCH_FELLOW_POSTDOC"} else "AMBIGUOUS",
                "dimensions": {
                    "scientific": "GOOD",
                    "level": level,
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


class CalibratedEvaluatorE021Tests(unittest.TestCase):
    def test_wellbeing_curriculum_school_name_does_not_create_apply(self):
        result = evaluate_calibrated(
            vacancy(
                title="Lecturer/Assistant Professor - Wellbeing in the Curriculum, UCD School of Public Health, Physiotherapy and Sports Science (SPHPSS)",
                role="ASSISTANT_PROFESSOR",
                level="ACCEPTABLE",
                jd="Lead a seed-funded whole-university project to embed wellbeing in the curriculum and student experience.",
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["dimensions"]["scientific"], "ADJACENT")

    def test_high_altitude_sport_physiology_postdoc_is_strong(self):
        result = evaluate_calibrated(
            vacancy(
                title="Universitätsassistent:in - Postdoc",
                jd=(
                    "Department of Sport Science. Independent research in high-altitude physiology and environmental physiology. "
                    "Research-led teaching in performance physiology and experience with magnetic resonance imaging."
                ),
            )
        )
        self.assertEqual(result["recommendation"], "STRONG_APPLY")
        self.assertEqual(result["dimensions"]["scientific"], "STRONG")

    def test_computational_neuroscience_machine_learning_is_not_apply(self):
        result = evaluate_calibrated(
            vacancy(
                title="Computational Neuroscience / Machine Learning",
                role="UNKNOWN",
                level="UNKNOWN",
                jd=(
                    "Postdoctoral research at the intersection of neuroscience and artificial intelligence, "
                    "developing machine learning and self-attention models for in-context learning."
                ),
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("ADVANCED_AI_ML_CENTRAL_E021", result["blocker_codes"])

    def test_clinical_psychology_professional_qualification_blocks(self):
        result = evaluate_calibrated(
            vacancy(
                title="Lecturer/Assistant Professor in Clinical Psychology",
                role="ASSISTANT_PROFESSOR",
                level="ACCEPTABLE",
                jd=(
                    "Applicants must have a doctorate in clinical psychology, or a PhD in psychology and an accredited professional "
                    "qualification in clinical psychology, and experience as a clinician in practice."
                ),
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("CLINICAL_PSYCHOLOGY_QUALIFICATION_E021", result["blocker_codes"])

    def test_mandatory_electrophysiology_blocks(self):
        result = evaluate_calibrated(
            vacancy(
                title="Postdoctoral Research Scientist in dopamine neuron physiology in Parkinson’s",
                jd=(
                    "The ideal candidate will hold a PhD in neurobiology and expertise in electrophysiological and/or photometry "
                    "techniques alongside genetic and pharmacological tools."
                ),
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("MANDATORY_ELECTROPHYSIOLOGY_E021", result["blocker_codes"])

    def test_immunologist_title_is_specialist_mismatch(self):
        result = evaluate_calibrated(
            vacancy(
                title="Post-Doctoral Researcher (Immunologist) - APC Microbiome Ireland",
                jd="Microbiome-gut-brain research requiring an immunologist to lead mechanistic immune experiments.",
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("SPECIALIST_BIOLOGY_TITLE_E021", result["blocker_codes"])

    def test_substantial_full_jd_without_profile_anchor_is_skip_not_low(self):
        result = evaluate_calibrated(
            vacancy(
                title="Postdoctoral Researcher in Applied Linguistics",
                jd=(
                    "This postdoctoral project investigates multilingual discourse, applied linguistics, language pedagogy, corpus analysis, "
                    "and sociolinguistic theory. The researcher will publish in linguistics journals, teach language modules, prepare conference "
                    "papers, collaborate with humanities scholars, conduct qualitative interviews, analyse textual corpora, and contribute to "
                    "departmental seminars and administration. The appointment requires a PhD in applied linguistics or a closely related field. "
                    "The successful applicant will develop independent linguistic research and support postgraduate language teaching."
                ),
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("NO_PROFILE_ANCHOR_IN_FULL_JD_E021", result["blocker_codes"])

    def test_brain_ageing_bioinformatics_is_recovered_to_review_not_skipped(self):
        result = evaluate_calibrated(
            vacancy(
                title="Bioinformatics Postdoctoral Scholarship within Brain aging",
                jd="Postdoctoral bioinformatics research on molecular signatures of brain aging and neurobiological ageing.",
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
