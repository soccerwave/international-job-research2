from __future__ import annotations

import unittest

from src.evaluation.calibrated_e021 import evaluate_calibrated


def vacancy(*, title: str, jd: str, role: str = "POSTDOC", level: str = "STRONG"):
    return {
        "position": {"title_raw": title, "role_family": role},
        "location": {"country_code": "DE"},
        "description": {"detail_status": "FULL", "full_jd": jd},
        "requirements": {},
        "raw_extra": {
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": "REVIEW",
                "pre_evaluation_disposition": "POLICY_REVIEW",
                "role_family": role,
                "role_policy_status": "PRIMARY",
                "dimensions": {
                    "scientific": "UNCLEAR",
                    "level": level,
                    "methods": "UNKNOWN",
                    "language": "CLEAR",
                    "mobility": "POTENTIALLY_VIABLE",
                    "registration": "CLEAR",
                    "contract": "UNKNOWN",
                },
                "fit_signals": [],
                "review_codes": ["UNCLEAR_DOMAIN"],
                "blocker_codes": [],
                "evidence": {},
                "reason": "baseline",
            }
        },
    }


class PositiveCalibrationTests(unittest.TestCase):
    def test_precision_neuroimaging_postdoc_promotes_to_apply_not_strong(self):
        jd = (
            "This postdoctoral project studies human memory and hippocampal function using precision neuroimaging, "
            "7T MRI and functional magnetic resonance imaging in adult participants. The researcher will analyse "
            "individual differences in memory performance, hippocampal structure and brain connectivity, work with "
            "human cognitive data, publish peer-reviewed papers, collaborate with neuroscientists and contribute to "
            "advanced MRI studies of cognition. The role requires a PhD and prior research experience in neuroscience."
        )
        result = evaluate_calibrated(vacancy(title="Postdoc Precision Neuroimaging", jd=jd))
        self.assertEqual(result["recommendation"], "APPLY")
        self.assertEqual(result["dimensions"]["scientific"], "GOOD")
        self.assertNotEqual(result["recommendation"], "STRONG_APPLY")

    def test_star_like_youth_mental_health_postdoc_promotes_to_apply(self):
        jd = (
            "The STAR project examines adolescent and youth mental health using large longitudinal cohort datasets. "
            "The postdoctoral researcher will study leisure practices, behavioural patterns, wellbeing and psychological "
            "outcomes in young people, analyse prospective survey data, publish findings and collaborate with a School "
            "of Psychology team. The project considers online and offline leisure, lifestyle behaviours and their "
            "associations with mental health across adolescence using cohort and longitudinal methods."
        )
        result = evaluate_calibrated(vacancy(title="Postdoctoral Researcher - STAR Project, School of Psychology", jd=jd))
        self.assertEqual(result["recommendation"], "APPLY")
        self.assertEqual(result["dimensions"]["scientific"], "GOOD")

    def test_animal_mri_memory_postdoc_is_not_promoted(self):
        jd = (
            "This postdoctoral project uses 7T MRI and functional MRI in mice and rodent animal models to investigate "
            "hippocampal memory circuits. The researcher will perform animal experiments, MRI acquisition, tissue work, "
            "behavioural assays and neuroscience analyses. The project focuses on mouse models and mechanistic animal "
            "research with repeated imaging and experimental interventions in rodents."
        )
        result = evaluate_calibrated(vacancy(title="Postdoctoral Researcher in MRI and Memory", jd=jd))
        self.assertNotEqual(result["recommendation"], "APPLY")

    def test_mri_physicist_is_not_promoted(self):
        jd = (
            "Develop magnetic resonance imaging pulse sequences, RF coil methods, image reconstruction pipelines and "
            "scanner quality assurance for a 7 Tesla MRI platform. The role is centred on MRI physics, sequence "
            "development, hardware optimisation, reconstruction and technical validation rather than behavioural or "
            "psychological research. The postdoctoral researcher will support advanced scanner engineering projects."
        )
        result = evaluate_calibrated(vacancy(title="Postdoctoral MRI Physicist", jd=jd))
        self.assertNotEqual(result["recommendation"], "APPLY")

    def test_generic_mental_health_postdoc_without_youth_design_is_not_promoted(self):
        jd = (
            "This postdoctoral role supports general mental health research and service evaluation across multiple adult "
            "clinical programmes. The researcher will prepare reports, coordinate stakeholders, support data management, "
            "assist publications and contribute to broad psychological health projects. The posting does not define a "
            "youth, adolescent, longitudinal, cohort, leisure, lifestyle or physical-activity research design."
        )
        result = evaluate_calibrated(vacancy(title="Postdoctoral Researcher in Mental Health", jd=jd))
        self.assertNotEqual(result["recommendation"], "APPLY")

    def test_clinical_psychology_qualification_still_blocks(self):
        jd = (
            "Applicants must have a doctorate in clinical psychology and an accredited professional qualification in "
            "clinical psychology, with experience as a clinician. The role includes adolescent mental health work, "
            "longitudinal outcome monitoring, clinical supervision and psychological assessment in youth services. "
            "Professional clinical practice and registration are central requirements of the appointment."
        )
        result = evaluate_calibrated(
            vacancy(title="Postdoctoral Researcher in Clinical Psychology", jd=jd)
        )
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("CLINICAL_PSYCHOLOGY_QUALIFICATION_E021", result["blocker_codes"])


if __name__ == "__main__":
    unittest.main()
