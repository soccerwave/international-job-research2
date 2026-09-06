from __future__ import annotations

import unittest

from src.evaluation.calibrated_e05 import evaluate_calibrated


def vacancy(*, title: str, jd: str, role: str = "POSTDOC", recommendation: str = "REVIEW", scientific: str = "ADJACENT", role_policy: str = "PRIMARY", blockers=None, reviews=None):
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
            "role_policy_status": role_policy,
            "dimensions": {"scientific": scientific, "level": "STRONG", "methods": "UNKNOWN", "language": "CLEAR", "mobility": "POTENTIALLY_VIABLE", "registration": "CLEAR", "contract": "UNKNOWN"},
            "review_codes": list(reviews or []),
            "blocker_codes": list(blockers or []),
            "evidence": {},
            "reason": "baseline"
        }}
    }


class E05GeneralizationTests(unittest.TestCase):
    def test_non_target_designer_is_not_rescued_by_science_employer_context(self):
        x = vacancy(
            title="Communication Designer - Biomedical Research Foundation",
            role="UNKNOWN",
            jd="Design visual communication for biomedical research, neuroscience, healthcare, scientific meetings and public engagement."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_navigation_shell_is_not_a_vacancy(self):
        x = vacancy(
            title="Find jobs and opportunities",
            role="UNKNOWN",
            jd="Research Field Cognitive science Neuroscience Public health Epidemiology Engineering Chemistry. Filter by country and research field."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_research_project_manager_remains_secondary_review_case(self):
        x = vacancy(
            title="Research Project Manager",
            role="PROJECT_MANAGER",
            jd="Coordinate a multidisciplinary health research consortium, grant reporting, work packages, deliverables and stakeholder communication."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_conditional_other_research_with_adjacent_fit_remains_reviewable(self):
        x = vacancy(
            title="Associate Scientist in Translational Neuroscience",
            role="OTHER_RESEARCH",
            role_policy="CONDITIONAL",
            recommendation="REVIEW",
            scientific="ADJACENT",
            jd=(
                "Translational neuroscience research using behavioural models and brain-health outcomes. "
                "Specialist molecular methods are preferred rather than required."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_conditional_other_research_without_relevance_is_not_rescued(self):
        x = vacancy(
            title="Associate Scientist in Polymer Chemistry",
            role="OTHER_RESEARCH",
            role_policy="CONDITIONAL",
            recommendation="REVIEW",
            scientific="WEAK",
            jd="Develop polymer synthesis workflows, catalyst chemistry and materials characterization for industrial applications.",
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_german_sport_science_postdoc_is_recovered_as_direct_fit(self):
        x = vacancy(
            title="Universitätsassistent*in Postdoc",
            role="POSTDOC",
            recommendation="REVIEW",
            scientific="UNCLEAR",
            jd=(
                "Zentrum für Sportwissenschaft und Universitätssport. Institut für Sport- und Bewegungswissenschaft. "
                "Abteilung Sportmedizin, Leistungsphysiologie und Prävention. Forschung in Leistungsphysiologie "
                "und Sportmedizin. Abgeschlossenes Doktorat auf dem Gebiet der Sportwissenschaft."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "STRONG_APPLY")

    def test_german_unrelated_physics_postdoc_is_not_rescued_by_language_support(self):
        x = vacancy(
            title="Universitätsassistent*in Postdoc",
            role="POSTDOC",
            jd="Institut für Quantenphysik. Forschung zu Quantenoptik, photonischen Materialien und Laserspektroskopie."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_stem_cell_transplantation_experience_is_hard_specialist_identity(self):
        x = vacancy(
            title="Research Fellow",
            jd=(
                "Postdoctoral work on gut and nervous system development. You will possess research experience "
                "in enteric nervous system models and evidenced experience in stem cell culture and in vivo transplantation techniques."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_informatics_llm_pdra_is_hard_specialist_identity(self):
        x = vacancy(
            title="Post-Doctoral Research Associates (PDRAs)",
            jd=(
                "School of Informatics. Research on novel architectures for Large Language Models and machine learning. "
                "Develop fundamental AI modelling methods, reinforcement learning hybrids, scalable training algorithms "
                "and train large models on multi-GPU distributed-computing infrastructure."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_exercise_role_with_mandatory_ephys_tms_emg_is_still_skip(self):
        x = vacancy(
            title="Research Fellow",
            jd=(
                "School of Sport, Exercise and Rehabilitation Sciences. Study exercise and neural mechanisms. "
                "High level analytical capability in electrophysiology and electromyography is essential. "
                "Fluency in TMS, EMG and functional electrical stimulation is required."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_exercise_role_with_preferred_ephys_is_not_hard_skip(self):
        x = vacancy(
            title="Postdoctoral Researcher in Exercise Physiology",
            recommendation="APPLY",
            scientific="STRONG",
            jd=(
                "Exercise physiology intervention research in adults. Experience with electrophysiology or EMG is preferred "
                "but not required. PhD in exercise science or related field."
            ),
        )
        self.assertIn(evaluate_calibrated(x)["recommendation"], {"STRONG_APPLY", "APPLY", "REVIEW"})

    def test_host_microbe_role_requiring_omics_and_genomics_is_skip(self):
        x = vacancy(
            title="Research Fellow",
            jd=(
                "Host-microbe interactions and microbiome research. You will have expertise in linking genomic variation to phenotype "
                "and hands-on experience with omics datasets including long-read sequencing. You are expected to integrate multi-omic datasets."
            ),
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")

    def test_microbiome_role_with_optional_omics_stays_surfaced(self):
        x = vacancy(
            title="Postdoctoral Researcher in Microbiome and Health",
            jd=(
                "Study microbiome and gut-brain health in a human cohort. Prior omics or genomic analysis experience is desirable "
                "and would be an asset, but it is not required."
            ),
        )
        self.assertIn(evaluate_calibrated(x)["recommendation"], {"STRONG_APPLY", "APPLY", "REVIEW"})

    def test_psychology_teaching_fellow_is_review_not_automatic_skip(self):
        x = vacancy(
            title="Teaching Fellow",
            role="LECTURER",
            jd="University School of Psychology. Teach undergraduate and postgraduate students within psychology subject areas."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "REVIEW")

    def test_law_teaching_fellow_is_skip(self):
        x = vacancy(
            title="Teaching Fellow",
            role="LECTURER",
            jd="School of Law. Teach international law, legal doctrine and public law modules."
        )
        self.assertEqual(evaluate_calibrated(x)["recommendation"], "SKIP")


if __name__ == "__main__":
    unittest.main()
