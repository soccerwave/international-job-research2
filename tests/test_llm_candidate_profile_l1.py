import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "llm_candidate_profile.schema.json").read_text(encoding="utf-8"))
PROFILE = json.loads((ROOT / "config" / "llm_candidate_profile_v1.json").read_text(encoding="utf-8"))


class LLMCandidateProfileL1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Draft202012Validator.check_schema(SCHEMA)
        cls.validator = Draft202012Validator(SCHEMA)

    def test_profile_validates(self):
        self.validator.validate(PROFILE)

    def test_profile_version_is_frozen_v1(self):
        self.assertEqual(PROFILE["profile_version"], "LLM_CANDIDATE_PROFILE_V1.0.0")

    def test_recall_priority_is_explicit(self):
        text = PROFILE["evaluation_guidance"]["recall_priority"].lower()
        self.assertIn("recall", text)
        self.assertIn("review", text)

    def test_transferable_fit_is_explicit(self):
        text = PROFILE["evaluation_guidance"]["transferable_fit"].lower()
        self.assertIn("transferable", text)
        self.assertIn("do not require exact keyword overlap", text)

    def test_neuroimaging_not_overclaimed(self):
        methods = {item["name"]: item for item in PROFILE["methods"]}
        self.assertEqual(methods["MRI and neuroimaging research"]["level"], "WORKING")
        self.assertEqual(methods["advanced independent fMRI preprocessing and analysis"]["level"], "DO_NOT_CLAIM")

    def test_exposure_is_not_promoted_to_strong(self):
        methods = {item["name"]: item for item in PROFILE["methods"]}
        self.assertEqual(methods["epigenetic research"]["level"], "EXPOSURE")
        self.assertEqual(methods["gut microbiota research"]["level"], "EXPOSURE")

    def test_required_do_not_infer_guardrails_exist(self):
        blocked = set(PROFILE["do_not_infer"])
        required = {
            "medical degree",
            "nursing degree",
            "professional healthcare registration",
            "citizenship or unrestricted work authorization in any country",
            "local-language proficiency beyond explicit evidence",
        }
        self.assertTrue(required.issubset(blocked))

    def test_unknown_method_level_rejected(self):
        bad = json.loads(json.dumps(PROFILE))
        bad["methods"][0]["level"] = "EXPERT"
        with self.assertRaises(ValidationError):
            self.validator.validate(bad)


if __name__ == "__main__":
    unittest.main()
