from __future__ import annotations

import unittest

from src.evaluation.calibrated_e021 import evaluate_calibrated


def vacancy(
    *,
    title: str,
    jd: str = "",
    role: str = "POSTDOC",
    level: str = "STRONG",
    detail_status: str = "FULL",
):
    return {
        "position": {"title_raw": title, "role_family": role},
        "description": {"detail_status": detail_status, "full_jd": jd},
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

    def test_high_altitude_specialist_physiology_is_review_not_auto_apply(self):
        result = evaluate_calibrated(
            vacancy(
                title="Universitätsassistent:in - Postdoc",
                jd=(
                    "Department of Sport Science. Independent research in high-altitude physiology and environmental physiology. "
                    "Research-led teaching in performance physiology and experience with magnetic resonance imaging."
                ),
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["dimensions"]["scientific"], "ADJACENT")
        self.assertIn("SPECIALIST_PHYSIOLOGY_ADJACENT_E022", result["review_codes"])

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

    def test_physiology_education_with_academic_strengths_is_review_not_skip(self):
        result = evaluate_calibrated(
            vacancy(
                title="Lecturer in Physiology Education",
                role="LECTURER",
                level="ACCEPTABLE",
                jd=(
                    "The successful applicant will contribute to undergraduate teaching in physiological sciences, including "
                    "cardiovascular physiology, respiratory physiology and neurophysiology. The role includes curriculum development, "
                    "supervision of undergraduate and postgraduate students, and contribution to student projects. Applicants should "
                    "have postdoctoral research experience, a record of peer-reviewed publications, and experience of university teaching. "
                    "The post combines education, scholarship and research within a physiology department."
                ),
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["dimensions"]["scientific"], "ADJACENT")
        self.assertIn("SECONDARY_PROFILE_EVIDENCE_REVIEW_E022", result["review_codes"])
        self.assertNotIn("NO_PROFILE_ANCHOR_IN_FULL_JD_E021", result["blocker_codes"])

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


    def test_psychology_teacher_is_not_promoted_by_adjacent_keyword(self):
        result = evaluate_calibrated(
            vacancy(
                title="Psychology Teacher & Portuguese as a Second Language",
                role="UNKNOWN",
                level="UNKNOWN",
                jd="Teach psychology and Portuguese language classes in a secondary-school setting.",
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("HIGH_CONFIDENCE_UNRELATED_TITLE_E02", result["blocker_codes"])

    def test_field_service_engineer_neuroscience_is_not_review(self):
        result = evaluate_calibrated(
            vacancy(
                title="Field Service Engineer – Microscopy (Neuroscience)",
                role="UNKNOWN",
                level="UNKNOWN",
                jd="Install, maintain and repair microscopy systems for neuroscience customers.",
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("HIGH_CONFIDENCE_UNRELATED_TITLE_E02", result["blocker_codes"])

    def test_stress_testing_associate_is_not_review(self):
        result = evaluate_calibrated(
            vacancy(
                title="Stress Testing Associate",
                role="UNKNOWN",
                level="UNKNOWN",
                jd="Support financial stress testing, capital planning and banking risk analysis.",
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("HIGH_CONFIDENCE_UNRELATED_TITLE_E02", result["blocker_codes"])

    def test_mental_health_nursing_occupational_identity_takes_precedence(self):
        result = evaluate_calibrated(
            vacancy(
                title="Lecturer in Mental Health Nursing",
                role="LECTURER",
                level="ACCEPTABLE",
                jd="Teach and supervise students in mental health nursing and professional nursing practice.",
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("HIGH_CONFIDENCE_UNRELATED_TITLE_E02", result["blocker_codes"])

    def test_mathematics_public_health_is_not_rescued_by_public_health(self):
        result = evaluate_calibrated(
            vacancy(
                title="Professor für Mathematik im Bereich Digital & Public Health",
                role="ASSISTANT_PROFESSOR",
                level="ACCEPTABLE",
                jd="Academic appointment centred on mathematics for digital and public health applications.",
            )
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("HIGH_CONFIDENCE_UNRELATED_TITLE_E02", result["blocker_codes"])

    def test_genuine_health_psychology_lecturer_remains_review(self):
        result = evaluate_calibrated(
            vacancy(
                title="Lecturer in Health Psychology",
                role="LECTURER",
                level="ACCEPTABLE",
                jd="University teaching and research in health psychology, behaviour and health outcomes.",
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertNotIn("HIGH_CONFIDENCE_UNRELATED_TITLE_E02", result["blocker_codes"])

    def test_target_postdoc_with_missing_detail_and_positive_title_stays_review(self):
        result = evaluate_calibrated(
            vacancy(
                title="Postdoctoral Researcher in Exercise Neuroscience",
                role="POSTDOC",
                level="STRONG",
                detail_status="NOT_ATTEMPTED",
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["pre_evaluation_disposition"], "NEEDS_DETAIL_REVIEW")

    def test_unknown_missing_detail_without_positive_profile_evidence_is_safety_net(self):
        result = evaluate_calibrated(
            vacancy(
                title="Project Associate",
                role="UNKNOWN",
                level="UNKNOWN",
                detail_status="NOT_ATTEMPTED",
            )
        )
        self.assertEqual(result["recommendation"], "LOW_PRIORITY")
        self.assertNotEqual(result["recommendation"], "REVIEW")


    def test_missing_detail_german_sport_psychology_academic_role_stays_review(self):
        result = evaluate_calibrated(
            vacancy(
                title="Universitätsprofesseur (W2) für Sportpsychologie",
                role="UNKNOWN",
                level="UNKNOWN",
                detail_status="UNAVAILABLE",
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")

    def test_missing_detail_german_health_and_movement_academic_role_stays_review(self):
        result = evaluate_calibrated(
            vacancy(
                title="Juniorprofessur (W1) für Gesundheit und Bewegung",
                role="JUNIOR_PROFESSOR",
                level="ACCEPTABLE",
                detail_status="UNAVAILABLE",
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")

    def test_missing_detail_german_sport_and_society_academic_role_stays_review(self):
        result = evaluate_calibrated(
            vacancy(
                title="Juniorprofessur (W1) für Sport und Gesellschaft",
                role="JUNIOR_PROFESSOR",
                level="ACCEPTABLE",
                detail_status="UNAVAILABLE",
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")


    def test_multi_signal_adjacent_research_title_is_not_blocked_by_ai_token(self):
        result = evaluate_calibrated(
            vacancy(
                title="Research Fellow, Data Scientist (Wearable Technologies, Digital Health & Artificial Intelligence)",
                role="RESEARCH_FELLOW_POSTDOC",
                level="ACCEPTABLE",
                jd="Research on wearable technologies and digital health methods using artificial intelligence.",
            )
        )
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertNotIn("HIGH_CONFIDENCE_UNRELATED_TITLE_E02", result["blocker_codes"])


if __name__ == "__main__":
    unittest.main()
