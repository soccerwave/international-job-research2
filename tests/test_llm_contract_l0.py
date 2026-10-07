import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from src.llm.shadow_evaluator import ShadowEvaluationError, _validate_output


ROOT = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = json.loads((ROOT / "schemas" / "llm_evaluator_input.schema.json").read_text(encoding="utf-8"))
OUTPUT_SCHEMA = json.loads((ROOT / "schemas" / "llm_evaluation.schema.json").read_text(encoding="utf-8"))


class LLMContractL0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Draft202012Validator.check_schema(INPUT_SCHEMA)
        Draft202012Validator.check_schema(OUTPUT_SCHEMA)
        cls.input_validator = Draft202012Validator(INPUT_SCHEMA)
        cls.output_validator = Draft202012Validator(OUTPUT_SCHEMA)

    def valid_input(self):
        return {
            "schema_version": "LLM_EVALUATOR_INPUT_V0.1",
            "evaluation_id": "eval-1",
            "candidate_profile_version": "CANDIDATE_PROFILE_V1",
            "job": {
                "job_id": "job-1",
                "title": "Research Fellow",
                "institution": "Example University",
                "location": "Barcelona",
                "country": "ES",
                "contract_type": "fixed-term",
                "seniority": "postdoctoral",
                "detail_status": "FULL",
                "full_text": "Full vacancy text with responsibilities and requirements.",
                "responsibilities_text": "Run research studies.",
                "essential_criteria_text": "PhD required.",
                "desirable_criteria_text": "Neuroimaging experience preferred.",
                "source_url": "https://example.org/job/1"
            }
        }

    def valid_output(self):
        return {
            "schema_version": "LLM_EVALUATION_V0.1",
            "evaluation_id": "eval-1",
            "decision": "APPLY",
            "fit_score": 84,
            "confidence": 81,
            "domain_fit": 88,
            "methods_fit": 79,
            "seniority_fit": 90,
            "eligibility_risk": "LOW",
            "transferable_fit": 86,
            "hard_blocker": False,
            "hard_blocker_reason": None,
            "reason_short": "Strong semantic fit based on the vacancy text and transferable methods.",
            "evidence_quality": "FULL_JD"
        }

    def test_valid_contract_examples_pass(self):
        self.input_validator.validate(self.valid_input())
        self.output_validator.validate(self.valid_output())

    def test_rule_based_decision_cannot_enter_llm_input(self):
        payload = self.valid_input()
        payload["rule_based_decision"] = "SKIP"
        with self.assertRaises(ValidationError):
            self.input_validator.validate(payload)

    def test_rule_based_score_cannot_enter_job_payload(self):
        payload = self.valid_input()
        payload["job"]["rule_score"] = 12
        with self.assertRaises(ValidationError):
            self.input_validator.validate(payload)

    def test_full_text_field_is_required_even_when_unavailable(self):
        payload = self.valid_input()
        del payload["job"]["full_text"]
        with self.assertRaises(ValidationError):
            self.input_validator.validate(payload)

    def test_hard_blocker_requires_reason(self):
        result = self.valid_output()
        result["hard_blocker"] = True
        result["hard_blocker_reason"] = None
        with self.assertRaises(ShadowEvaluationError):
            _validate_output(result, result["evaluation_id"])

    def test_decision_vocabulary_is_closed(self):
        result = self.valid_output()
        result["decision"] = "MAYBE"
        with self.assertRaises(ValidationError):
            self.output_validator.validate(result)

    def test_scores_are_bounded(self):
        result = self.valid_output()
        result["fit_score"] = 101
        with self.assertRaises(ValidationError):
            self.output_validator.validate(result)


if __name__ == "__main__":
    unittest.main()
