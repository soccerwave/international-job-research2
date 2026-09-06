from __future__ import annotations

import unittest

from src.evaluation.calibrated_e042 import evaluate_calibrated


def vacancy(*, title: str, jd: str, role: str = "POSTDOC", recommendation: str = "REVIEW", scientific: str = "ADJACENT", blockers=None, reviews=None):
    return {
        "canonical_id": "synthetic",
        "position": {"title_raw": title, "role_family": role},
        "location": {"country_code": "GB", "country_name": "United Kingdom"},
        "dates": {},
        "source": {"retrieved_at": "2026-09-05T00:00:00+00:00", "source_key": "test"},
        "description": {"detail_status": "FULL", "full_jd": jd},
        "requirements": {},
        "raw_extra": {"evaluation": {
            "evaluator_version": "E0.1",
            "recommendation": recommendation,
            "pre_evaluation_disposition": "POLICY_REVIEW",
            "role_family": role,
            "role_policy_status": "PRIMARY",
            "dimensions": {"scientific": scientific, "level": "STRONG", "methods": "UNKNOWN", "language": "CLEAR", "mobility": "POTENTIALLY_VIABLE", "registration": "CLEAR", "contract": "UNKNOWN"},
            "review_codes": list(reviews or []),
            "blocker_codes": list(blockers or []),
            "evidence": {},
            "reason": "baseline"
        }}
    }


class E042GeneralizationTests(unittest.TestCase):
    def test_explicit_phd_role_is_not_rescued_by_neuroscience(self):
        x = vacancy(title="Multiple PhD positions in Brain and Behavior", role="OTHER_RESEARCH", blockers=["ROLE_STUDENT_E02"], jd="Fully funded PhD training in neuroscience and brain circuits. Master's degree required.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_unrelated_archaeology_ai_title_is_not_rescued_by_body_noise(self):
        x = vacancy(title="Postdoctoral Researcher in Archaeology and AI", blockers=["HIGH_CONFIDENCE_UNRELATED_TITLE_E02"], jd="Archaeological prospection using artificial intelligence and predictive models. University wellbeing and physical activity benefits are available.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_adjunct_health_pool_is_out_of_scope(self):
        x = vacancy(title="Adjunct Appointments & Adjunct Clinical Appointments (New), College of Medicine & Health", role="UNKNOWN", jd="Open call for honorary adjunct professor, adjunct lecturer and adjunct clinical lecturer appointments across Medicine, Public Health and Clinical Therapies.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_required_advanced_fmri_is_hard_mismatch(self):
        x = vacancy(title="University Assistant postdoctoral", jd="Cognitive neuroscience of language. Experience in advanced analysis of fMRI, resting-state connectivity and fMRIPrep pipelines is required. PhD in Biology.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_preferred_advanced_fmri_is_not_hard_mismatch(self):
        x = vacancy(title="Postdoctoral Researcher in Cognitive Neuroscience", jd="Research on cognition and brain networks. Experience in advanced analysis of fMRI would be desirable, but it is not required. PhD in a health or neuroscience field.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_bioinformatics_title_plus_omics_methods_is_specialist_identity(self):
        x = vacancy(title="Bioinformatics Postdoctoral Scholarship within Brain Aging", jd="Brain aging project using bioinformatics, genomics, transcriptomics, single-cell and long-read datasets. Strong programming skills required.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_computational_neuroscience_title_plus_central_methods_is_specialist_identity(self):
        x = vacancy(title="Postdoctoral Fellows in computational neuroscience", jd="Develop and implement computational models for high-density neural recordings. Technical skills include advanced signal processing and detailed biophysical modelling.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_nhp_vision_central_experimental_system_is_specialist_identity(self):
        x = vacancy(title="Postdoctoral associate in NHP vision lab", jd="Work with non-human primates. The lab uses electrophysiological recording, microstimulation and chronically implanted neuroprostheses with thousands of electrodes.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_mrna_immunotherapy_postdoc_is_specialist_identity_not_project_management(self):
        x = vacancy(title="Postdoctoral Research Fellow - mRNA Cancer Immunotherapy", jd="Lead an mRNA cancer vaccine research program. PhD in mRNA sciences, molecular biology or immunology. Develop cancer immunotherapy and cancer vaccines and apply for research funding.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_incidental_grant_duties_do_not_create_secondary_track(self):
        x = vacancy(title="Research Fellow, Disability and Digital Citizenship", role="RESEARCH_FELLOW_POSTDOC", jd="Research in disability studies and digital citizenship. Lead surveys, publications and community engagement. Contribute to research funding applications and project administration. PhD in disability studies or media studies.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_preference_will_be_given_is_not_mandatory(self):
        x = vacancy(title="Associate Scientist in Translational Studies in Schizophrenia Models", role="RESEARCH_SCIENTIST", jd="Neural circuits and schizophrenia research. Preference will be given to applicants with a PhD in neuroscience who have a strong background in molecular biology, ASO biochemistry, 2-photon imaging or stereotaxic injections.")
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
