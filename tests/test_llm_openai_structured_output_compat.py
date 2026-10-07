from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.llm.shadow_evaluator import ShadowEvaluationError, ShadowEvaluator, build_llm_input
from tests.test_llm_shadow_evaluator_l2 import FakeTransport, PROFILE, canonical_job, valid_result

ROOT = Path(__file__).resolve().parents[1]


class OpenAIStructuredOutputCompatibilityTests(unittest.TestCase):
    def test_schemas_avoid_unsupported_strict_composition_keywords(self):
        unsupported = {"allOf", "not", "dependentRequired", "dependentSchemas", "if", "then", "else"}
        for rel in (
            "schemas/llm_rescue_triage.schema.json",
            "schemas/llm_evaluation.schema.json",
        ):
            schema = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            serialized = json.dumps(schema)
            for keyword in unsupported:
                self.assertNotIn(f'"{keyword}"', serialized, msg=f"{rel} contains {keyword}")

    def test_const_schema_version_has_explicit_string_type(self):
        for rel in (
            "schemas/llm_rescue_triage.schema.json",
            "schemas/llm_evaluation.schema.json",
        ):
            schema = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            version = schema["properties"]["schema_version"]
            self.assertEqual(version["type"], "string")
            self.assertIn("const", version)

    def test_hard_blocker_still_requires_reason_in_local_validation(self):
        job = canonical_job()
        llm_input = build_llm_input(job, PROFILE)
        result = valid_result()
        result["evaluation_id"] = llm_input["evaluation_id"]
        result["hard_blocker"] = True
        result["hard_blocker_reason"] = None
        evaluator = ShadowEvaluator(
            transport=FakeTransport(result),
            candidate_profile=PROFILE,
        )
        with self.assertRaises(ShadowEvaluationError):
            evaluator.evaluate(job)


if __name__ == "__main__":
    unittest.main()
