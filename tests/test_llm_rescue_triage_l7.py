from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.llm.rescue_triage import (
    CLEARLY_OUT_OF_SCOPE,
    PASS_TO_FULL_REVIEW,
    RescueTriageError,
    RescueTriageEvaluator,
    build_rescue_triage_input,
)
from src.llm.shadow_evaluator import LLMResponse


def profile() -> dict:
    return {
        "profile_version": "TEST_PROFILE_V1",
        "evidence_profile": {
            "career_stage": {
                "current_level": "POSTDOCTORAL_RESEARCHER",
                "summary": "Exercise neuroscience researcher.",
            },
            "education": [
                {"degree": "PhD", "field": "Exercise Physiology"},
            ],
        },
        "search_preferences": {
            "target_role_families": ["POSTDOC", "RESEARCH_SCIENTIST"],
            "core_domains": ["exercise neuroscience", "exercise physiology"],
            "adjacent_domains": ["behavioral medicine", "mental health", "rehabilitation"],
        },
    }


def job(job_id: str, title: str = "Postdoctoral Research Fellow") -> dict:
    return {
        "canonical_id": job_id,
        "position": {
            "title_raw": title,
            "institution_raw": "Example University",
            "department": "School of Health",
            "role_family": "POSTDOC",
            "role_level": "POSTDOC",
            "employment_type": "FULL_TIME",
        },
        "location": {"country_code": "DE", "city": "Berlin"},
        "contract": {"term_type": "FIXED_TERM"},
        "description": {
            "full_jd": "SECRET_FULL_JD_MARKER " * 50,
            "responsibilities_text": "SECRET_RESPONSIBILITY_MARKER",
            "essential_criteria_text": "SECRET_ESSENTIAL_MARKER",
        },
        "raw_extra": {
            "evaluation": {
                "recommendation": "SKIP",
                "reason": "SECRET_RULE_REASON_MARKER",
            },
            "department": "School of Health",
        },
        "source": {"detail_url": "https://example.org/job/1"},
    }


class FakeTransport:
    def __init__(self, decision: str = PASS_TO_FULL_REVIEW, *, identity: str = "fake:luna") -> None:
        self.decision = decision
        self.cache_identity = identity
        self.calls: list[dict] = []

    def generate(self, *, system_prompt, user_prompt, response_schema):
        payload = json.loads(user_prompt)
        triage_material = json.dumps(payload, sort_keys=True)
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_schema": response_schema,
            }
        )
        triage_id = build_rescue_triage_input(
            self.current_job,
            self.current_profile,
        ).triage_id
        return LLMResponse(
            text=json.dumps(
                {
                    "schema_version": "LLM_RESCUE_TRIAGE_V0.1",
                    "triage_id": triage_id,
                    "decision": self.decision,
                    "reason_short": "Routing decision based only on limited metadata.",
                }
            ),
            model="gpt-6-luna",
            input_tokens=max(1, len(triage_material) // 4),
            output_tokens=40,
            latency_ms=10,
        )


class RescueTriageL7Tests(unittest.TestCase):
    def _evaluate(self, transport: FakeTransport, candidate_profile: dict, vacancy: dict, cache_path=None):
        transport.current_job = vacancy
        transport.current_profile = candidate_profile
        evaluator = RescueTriageEvaluator(
            transport=transport,
            candidate_profile=candidate_profile,
            cache_path=cache_path,
        )
        return evaluator.evaluate(vacancy)

    def test_triage_input_excludes_full_jd_and_rule_evaluation(self):
        candidate = profile()
        vacancy = job("j1")
        built = build_rescue_triage_input(vacancy, candidate)
        serialized = json.dumps(
            {
                "metadata": built.metadata,
                "candidate_summary": built.candidate_summary,
            },
            sort_keys=True,
        )
        self.assertNotIn("SECRET_FULL_JD_MARKER", serialized)
        self.assertNotIn("SECRET_RESPONSIBILITY_MARKER", serialized)
        self.assertNotIn("SECRET_ESSENTIAL_MARKER", serialized)
        self.assertNotIn("SECRET_RULE_REASON_MARKER", serialized)
        self.assertNotIn("recommendation", serialized)

    def test_prompt_is_binary_and_recall_first_on_uncertainty(self):
        candidate = profile()
        vacancy = job("j2", "Research Fellow")
        transport = FakeTransport(PASS_TO_FULL_REVIEW)
        result = self._evaluate(transport, candidate, vacancy)
        self.assertEqual(result["llm_result"]["decision"], PASS_TO_FULL_REVIEW)
        system_prompt = transport.calls[0]["system_prompt"]
        user_payload = json.loads(transport.calls[0]["user_prompt"])
        schema = transport.calls[0]["response_schema"]
        self.assertIn("When uncertain, always return PASS_TO_FULL_REVIEW", system_prompt)
        self.assertEqual(user_payload["triage_id"], build_rescue_triage_input(vacancy, candidate).triage_id)
        self.assertEqual(
            schema["properties"]["decision"]["enum"],
            [PASS_TO_FULL_REVIEW, CLEARLY_OUT_OF_SCOPE],
        )
        self.assertNotIn("UNCERTAIN", json.dumps(schema))

    def test_clearly_out_of_scope_is_valid(self):
        candidate = profile()
        vacancy = job("j3", "Lecturer in Medieval History")
        transport = FakeTransport(CLEARLY_OUT_OF_SCOPE)
        result = self._evaluate(transport, candidate, vacancy)
        self.assertEqual(result["llm_result"]["decision"], CLEARLY_OUT_OF_SCOPE)

    def test_invalid_third_decision_is_rejected(self):
        candidate = profile()
        vacancy = job("j4")

        class InvalidTransport(FakeTransport):
            def generate(self, *, system_prompt, user_prompt, response_schema):
                self.calls.append(
                    {
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                        "response_schema": response_schema,
                    }
                )
                triage_id = build_rescue_triage_input(self.current_job, self.current_profile).triage_id
                return LLMResponse(
                    text=json.dumps(
                        {
                            "schema_version": "LLM_RESCUE_TRIAGE_V0.1",
                            "triage_id": triage_id,
                            "decision": "UNCERTAIN",
                            "reason_short": "uncertain",
                        }
                    )
                )

        transport = InvalidTransport()
        with self.assertRaises(RescueTriageError):
            self._evaluate(transport, candidate, vacancy)

    def test_successful_triage_is_cached_and_not_called_twice(self):
        candidate = profile()
        vacancy = job("j5")
        transport = FakeTransport(PASS_TO_FULL_REVIEW)
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.jsonl"
            transport.current_job = vacancy
            transport.current_profile = candidate
            evaluator = RescueTriageEvaluator(
                transport=transport,
                candidate_profile=candidate,
                cache_path=cache_path,
            )
            first = evaluator.evaluate(vacancy)
            second = evaluator.evaluate(vacancy)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(len(transport.calls), 1)

    def test_metadata_change_invalidates_cache(self):
        candidate = profile()
        original = job("j6", "Research Fellow")
        changed = copy.deepcopy(original)
        changed["position"]["title_raw"] = "Postdoctoral Fellow in Behavioral Medicine"
        transport = FakeTransport(PASS_TO_FULL_REVIEW)
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.jsonl"
            transport.current_profile = candidate
            evaluator = RescueTriageEvaluator(
                transport=transport,
                candidate_profile=candidate,
                cache_path=cache_path,
            )
            transport.current_job = original
            evaluator.evaluate(original)
            transport.current_job = changed
            evaluator.evaluate(changed)
            self.assertEqual(len(transport.calls), 2)

    def test_model_identity_change_invalidates_cache(self):
        candidate = profile()
        vacancy = job("j7")
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.jsonl"
            first_transport = FakeTransport(PASS_TO_FULL_REVIEW, identity="fake:luna-a")
            self._evaluate(first_transport, candidate, vacancy, cache_path=cache_path)
            second_transport = FakeTransport(PASS_TO_FULL_REVIEW, identity="fake:luna-b")
            result = self._evaluate(second_transport, candidate, vacancy, cache_path=cache_path)
            self.assertFalse(result["cache_hit"])
            self.assertEqual(len(second_transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
