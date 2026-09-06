import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from src.evaluation import evaluate_vacancy

ROOT = Path(__file__).resolve().parents[1]
EVAL_SCHEMA = json.loads((ROOT / "schemas" / "evaluation.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(EVAL_SCHEMA)


def base_job(title="Postdoctoral Researcher in Exercise Physiology", country="NL", jd=None):
    if jd is None:
        jd = (
            "We seek a postdoctoral researcher with a PhD in exercise physiology. "
            "The project studies physical activity, fitness and human exercise interventions. "
            "Experience with randomized controlled trials, physiological assessment and statistics is desirable."
        )
    return {
        "schema_version": "VACANCY_SCHEMA_V1.0.0",
        "record_stage": "SHARD_ENRICHED",
        "source_record_id": "test:1",
        "canonical_id": None,
        "source": {
            "source_key": "fixture",
            "source_kind": "DIRECT_INSTITUTION",
            "provider": "Fixture University",
            "source_job_id": "1",
            "listing_url": "https://example.org/jobs/1",
            "detail_url": "https://example.org/jobs/1",
            "apply_url": "https://example.org/jobs/1/apply",
            "retrieved_at": "2026-09-04T12:00:00Z",
            "source_language": "en",
            "source_status": "OPEN",
        },
        "position": {
            "title_raw": title,
            "title_normalized": None,
            "institution_raw": "Fixture University",
            "institution_normalized": None,
            "department": None,
            "role_family": "UNKNOWN",
            "role_level": "UNKNOWN",
            "employment_type": "FULL_TIME",
            "workplace_mode": "ONSITE",
        },
        "location": {"country_code": country, "country_name": None, "city": None, "region": None},
        "dates": {
            "posted_at": None,
            "deadline_at": None,
            "deadline_text": None,
            "deadline_status": "UNKNOWN",
            "collected_at": "2026-09-04T12:00:00Z",
        },
        "contract": {
            "term_type": "FIXED_TERM",
            "duration_months": 24,
            "fte": 1.0,
            "salary": {"min": None, "max": None, "currency": None, "period": "UNKNOWN", "raw_text": None},
        },
        "description": {
            "full_jd": jd,
            "detail_status": "FULL" if jd else "UNAVAILABLE",
            "detail_failure_reason": None if jd else "fixture missing detail",
            "detail_retrieved_at": "2026-09-04T12:00:00Z" if jd else None,
        },
        "requirements": {
            "phd_requirement": "REQUIRED",
            "degree_text": "PhD in exercise physiology or related field",
            "degree_fields": ["exercise physiology"],
            "years_postdoc": None,
            "language_requirements": [],
            "work_rights_text": None,
            "sponsorship_text": None,
            "professional_registration_text": None,
            "teaching_requirement_text": None,
            "methods_required": [],
            "methods_preferred": [],
        },
        "classification": {
            "market_tier": "CORE",
            "role_policy_status": "AMBIGUOUS",
            "pre_evaluation_disposition": "ELIGIBLE_FOR_EVALUATION",
            "review_codes": [],
            "blocker_codes": [],
        },
        "provenance": {"observed_by_sources": ["fixture"], "raw_payload_fingerprint": None, "notes": []},
    }


class Stage7EvaluatorTests(unittest.TestCase):
    def evaluate(self, job):
        result = evaluate_vacancy(job)
        errors = list(VALIDATOR.iter_errors(result))
        self.assertFalse(errors, "; ".join(e.message for e in errors))
        return result

    def test_core_exercise_postdoc_is_strong_apply(self):
        result = self.evaluate(base_job())
        self.assertEqual(result["recommendation"], "STRONG_APPLY")
        self.assertEqual(result["dimensions"]["scientific"], "STRONG")
        self.assertEqual(result["dimensions"]["level"], "STRONG")

    def test_core_exercise_neuroscience_postdoc_is_strong(self):
        job = base_job(
            title="Postdoctoral Fellow in Exercise Neuroscience and Stress Biology",
            jd="PhD required. Research on exercise neuroscience, brain health, psychosocial stress, cortisol, cognition and human interventions.",
        )
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "STRONG_APPLY")
        self.assertEqual(result["dimensions"]["scientific"], "STRONG")

    def test_adjacent_health_role_is_review_not_skip(self):
        job = base_job(
            title="Postdoctoral Researcher in Behavioral Health",
            jd="Postdoctoral research on behavioral health, health promotion and behavior change interventions in adults.",
        )
        job["requirements"]["degree_text"] = "PhD in health sciences or related field"
        job["requirements"]["degree_fields"] = ["health sciences"]
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["dimensions"]["scientific"], "ADJACENT")

    def test_generic_research_fellow_routes_to_review(self):
        job = base_job(title="Research Fellow", jd="Research Fellow working on physical activity and health research in adults.")
        job["requirements"]["phd_requirement"] = "UNKNOWN"
        job["requirements"]["degree_text"] = None
        job["requirements"]["degree_fields"] = []
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertIn("GENERIC_RESEARCH_FELLOW", result["review_codes"])

    def test_missing_full_jd_is_review_even_with_good_title(self):
        job = base_job(jd="")
        job["description"]["full_jd"] = None
        job["description"]["detail_status"] = "FETCH_FAILED"
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["pre_evaluation_disposition"], "NEEDS_DETAIL_REVIEW")
        self.assertIn("FULL_JD_UNAVAILABLE", result["review_codes"])

    def test_france_faculty_is_explicit_skip(self):
        job = base_job(title="Maître de conférences en physiologie de l'exercice", country="FR")
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("FR_FACULTY_OUT_OF_SCOPE", result["blocker_codes"])

    def test_student_role_is_explicit_skip(self):
        job = base_job(title="PhD Candidate in Exercise Physiology")
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("ROLE_STUDENT", result["blocker_codes"])

    def test_mandatory_professional_registration_blocks(self):
        job = base_job(title="Lecturer in Clinical Exercise Physiology", country="AU")
        job["requirements"]["professional_registration_text"] = "Current AHPRA registration is required."
        job["description"]["full_jd"] += " Current AHPRA registration is required."
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("MANDATORY_PROFESSIONAL_REGISTRATION", result["blocker_codes"])

    def test_german_c1_c2_teaching_is_explicit_skip(self):
        job = base_job(title="Juniorprofessor für Sportwissenschaft", country="DE")
        job["requirements"]["language_requirements"] = [
            {"language": "German", "level": "C1", "mandatory": True, "raw_text": "German C1 is mandatory"}
        ]
        job["requirements"]["teaching_requirement_text"] = "Teaching undergraduate courses is required."
        job["description"]["full_jd"] += " German C1 is mandatory for teaching."
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("MANDATORY_GERMAN_C1_C2_TEACHING", result["blocker_codes"])

    def test_australia_no_sponsorship_plus_work_rights_blocks(self):
        job = base_job(country="AU")
        job["requirements"]["sponsorship_text"] = "No visa sponsorship is available."
        job["requirements"]["work_rights_text"] = "Applicants must already have unrestricted work rights in Australia."
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("AU_NO_SPONSORSHIP_WORK_RIGHTS_REQUIRED", result["blocker_codes"])

    def test_patch_clamp_required_is_explicit_skip(self):
        job = base_job(
            title="Postdoctoral Researcher in Neuroscience",
            jd="A PhD is required. Strong hands-on patch-clamp experience is essential for this neuronal electrophysiology project.",
        )
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("MANDATORY_PATCH_CLAMP", result["blocker_codes"])

    def test_advanced_ai_ml_required_is_explicit_skip(self):
        job = base_job(
            title="Postdoctoral Researcher in AI for Medical Imaging",
            jd="A PhD is required. Advanced machine learning expertise is essential. Strong experience with Python and PyTorch is required for deep learning and computer vision research.",
        )
        job["requirements"]["degree_text"] = "PhD in computer science or related field"
        job["requirements"]["degree_fields"] = ["computer science"]
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("MANDATORY_ADVANCED_AI_ML", result["blocker_codes"])

    def test_preferred_mri_is_not_a_blocker(self):
        job = base_job()
        job["requirements"]["methods_preferred"] = ["MRI"]
        job["description"]["full_jd"] += " MRI experience is desirable but not required."
        result = self.evaluate(job)
        self.assertNotEqual(result["recommendation"], "SKIP")
        self.assertNotIn("MANDATORY_ADVANCED_AI_ML", result["blocker_codes"])

    def test_mobility_silence_in_netherlands_is_not_blocker(self):
        job = base_job(country="NL")
        result = self.evaluate(job)
        self.assertEqual(result["dimensions"]["mobility"], "POTENTIALLY_VIABLE")
        self.assertNotEqual(result["recommendation"], "SKIP")

    def test_uk_no_sponsorship_routes_to_review_not_skip(self):
        job = base_job(country="GB")
        job["requirements"]["sponsorship_text"] = "Visa sponsorship is not available for this post."
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["dimensions"]["mobility"], "REVIEW")
        self.assertFalse(result["blocker_codes"])

    def test_senior_professor_is_low_priority_not_hard_skip(self):
        job = base_job(title="Professor of Exercise Physiology")
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "LOW_PRIORITY")
        self.assertFalse(result["blocker_codes"])

    def test_secondary_research_scientist_routes_to_review(self):
        job = base_job(title="Research Scientist in Physical Activity and Brain Health")
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertEqual(result["role_policy_status"], "SECONDARY")

    def test_mandatory_advanced_fmri_analysis_is_review_not_inferred(self):
        job = base_job(
            title="Postdoctoral Researcher in Exercise and Brain Health",
            jd="A PhD is required. Advanced independent fMRI preprocessing and analysis experience is essential. The project studies exercise and brain health.",
        )
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertIn("ADVANCED_FMRI_ANALYSIS_NOT_ESTABLISHED", result["review_codes"])
        self.assertNotEqual(result["recommendation"], "SKIP")

    def test_mandatory_local_language_without_profile_evidence_is_review(self):
        job = base_job(country="NL")
        job["requirements"]["language_requirements"] = [
            {"language": "Dutch", "level": "C1", "mandatory": True, "raw_text": "Dutch C1 required"}
        ]
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "REVIEW")
        self.assertIn("LOCAL_LANGUAGE_MANDATORY_UNCONFIRMED", result["review_codes"])

    def test_explicit_unrelated_domain_with_full_jd_can_skip(self):
        job = base_job(
            title="Lecturer in Marketing",
            jd="The role is in marketing and corporate finance with research in consumer marketing and accounting. A PhD in marketing is required.",
        )
        job["requirements"]["degree_text"] = "PhD in marketing"
        job["requirements"]["degree_fields"] = ["marketing"]
        result = self.evaluate(job)
        self.assertEqual(result["recommendation"], "SKIP")
        self.assertIn("HIGH_CONFIDENCE_UNRELATED_DOMAIN", result["blocker_codes"])


if __name__ == "__main__":
    unittest.main()
