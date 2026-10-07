from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.llm.shadow_evaluator import LLMResponse, ShadowEvaluationError, ShadowEvaluator, build_llm_input

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "config" / "llm_candidate_profile_v1.json").read_text(encoding="utf-8"))


def canonical_job(*, detail_status: str = "FULL", full_jd: str | None = None) -> dict:
    if full_jd is None and detail_status in {"FULL", "PARTIAL"}:
        full_jd = (
            "Postdoctoral researcher in psychophysiology and health behavior. Responsibilities include human intervention research, "
            "stress-related outcomes, physiological assessment, data analysis and collaboration. A PhD in a relevant field is essential. "
            "Neuroimaging experience is desirable but not mandatory."
        )
    return {
        "source_record_id": "test:123",
        "canonical_id": "canonical-123",
        "source": {
            "listing_url": "https://example.org/jobs/123",
            "detail_url": "https://example.org/jobs/123",
        },
        "position": {
            "title_raw": "Postdoctoral Researcher",
            "institution_raw": "Example University",
            "role_level": "POSTDOC",
            "employment_type": "FULL_TIME",
        },
        "location": {"city": "Barcelona", "country_code": "ES", "country_name": "Spain"},
        "contract": {"term_type": "FIXED_TERM"},
        "description": {"full_jd": full_jd, "detail_status": detail_status},
        "requirements": {},
        "raw_extra": {},
        "classification": {
            "pre_evaluation_disposition": "SKIP",
            "review_codes": ["rule-output-that-must-not-leak"],
        },
    }


class FakeTransport:
    def __init__(self, response: dict | str | Exception, *, cache_identity: str = "fake:cheap-model"):
        self.response = response
        self.system_prompt = None
        self.user_prompt = None
        self.cache_identity = cache_identity
        self.calls = 0

    def generate(self, *, system_prompt, user_prompt, response_schema):
        self.calls += 1
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        if isinstance(self.response, Exception):
            raise self.response
        text = self.response if isinstance(self.response, str) else json.dumps(self.response)
        return LLMResponse(text=text, model="fake-cheap-model", input_tokens=900, output_tokens=140, latency_ms=25)


def valid_result(*, confidence: int = 88, evidence_quality: str = "FULL_JD") -> dict:
    return {
        "schema_version": "LLM_EVALUATION_V0.1",
        "evaluation_id": "placeholder",
        "decision": "APPLY",
        "fit_score": 82,
        "confidence": confidence,
        "domain_fit": 85,
        "methods_fit": 80,
        "seniority_fit": 90,
        "eligibility_risk": "LOW",
        "transferable_fit": 88,
        "hard_blocker": False,
        "hard_blocker_reason": None,
        "reason_short": "Strong adjacent fit based on human intervention, stress, physiology and research methods; neuroimaging is only desirable.",
        "evidence_quality": evidence_quality,
    }


class LLMShadowEvaluatorL2Tests(unittest.TestCase):
    def test_input_is_independent_from_rule_evaluator(self):
        payload = build_llm_input(canonical_job(), PROFILE)
        serialized = json.dumps(payload)
        self.assertNotIn("pre_evaluation_disposition", serialized)
        self.assertNotIn("review_codes", serialized)
        self.assertNotIn("SKIP", serialized)
        self.assertIn("psychophysiology", payload["job"]["full_text"])

    def test_profile_version_is_bound_to_evaluation(self):
        payload = build_llm_input(canonical_job(), PROFILE)
        self.assertEqual(payload["candidate_profile_version"], "LLM_CANDIDATE_PROFILE_V1.1.0")
        self.assertTrue(payload["evaluation_id"])

    def test_full_jd_and_candidate_profile_are_sent_to_model(self):
        llm_input = build_llm_input(canonical_job(), PROFILE)
        result = valid_result()
        result["evaluation_id"] = llm_input["evaluation_id"]
        transport = FakeTransport(result)
        evaluator = ShadowEvaluator(transport=transport, candidate_profile=PROFILE)
        evaluator.evaluate(canonical_job())
        self.assertIn("psychophysiology", transport.user_prompt)
        self.assertIn("LLM_CANDIDATE_PROFILE_V1.1.0", transport.user_prompt)
        self.assertIn(llm_input["evaluation_id"], transport.user_prompt)
        self.assertNotIn("pre_evaluation_disposition", transport.user_prompt)

    def test_missing_jd_caps_confidence_and_marks_insufficient(self):
        job = canonical_job(detail_status="UNAVAILABLE", full_jd="")
        llm_input = build_llm_input(job, PROFILE)
        result = valid_result(confidence=95, evidence_quality="FULL_JD")
        result["evaluation_id"] = llm_input["evaluation_id"]
        evaluator = ShadowEvaluator(transport=FakeTransport(result), candidate_profile=PROFILE)
        stored = evaluator.evaluate(job)
        self.assertEqual(stored["llm_result"]["evidence_quality"], "INSUFFICIENT")
        self.assertEqual(stored["llm_result"]["confidence"], 30)

    def test_partial_jd_caps_confidence(self):
        job = canonical_job(detail_status="PARTIAL", full_jd="Partial source text")
        llm_input = build_llm_input(job, PROFILE)
        result = valid_result(confidence=95)
        result["evaluation_id"] = llm_input["evaluation_id"]
        stored = ShadowEvaluator(transport=FakeTransport(result), candidate_profile=PROFILE).evaluate(job)
        self.assertEqual(stored["llm_result"]["evidence_quality"], "PARTIAL_JD")
        self.assertEqual(stored["llm_result"]["confidence"], 80)

    def test_shadow_storage_is_separate_jsonl(self):
        job = canonical_job()
        llm_input = build_llm_input(job, PROFILE)
        result = valid_result()
        result["evaluation_id"] = llm_input["evaluation_id"]
        with tempfile.TemporaryDirectory() as tmp:
            shadow = Path(tmp) / "shadow.jsonl"
            telemetry = Path(tmp) / "telemetry.jsonl"
            evaluator = ShadowEvaluator(
                transport=FakeTransport(result),
                candidate_profile=PROFILE,
                shadow_path=shadow,
                telemetry_path=telemetry,
            )
            stored = evaluator.evaluate(job)
            rows = [json.loads(line) for line in shadow.read_text(encoding="utf-8").splitlines()]
            events = [json.loads(line) for line in telemetry.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["evaluation_id"], stored["evaluation_id"])
            self.assertEqual(rows[0]["llm_result"]["decision"], "APPLY")
            self.assertEqual([x["event"] for x in events], ["llm_evaluation_start", "llm_evaluation_stored"])

    def test_malformed_json_is_telemetried(self):
        with tempfile.TemporaryDirectory() as tmp:
            telemetry = Path(tmp) / "telemetry.jsonl"
            evaluator = ShadowEvaluator(
                transport=FakeTransport("not-json"),
                candidate_profile=PROFILE,
                telemetry_path=telemetry,
            )
            with self.assertRaises(ShadowEvaluationError):
                evaluator.evaluate(canonical_job())
            events = [json.loads(line) for line in telemetry.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events[-1]["event"], "llm_response_invalid")

    def test_api_failure_is_telemetried(self):
        with tempfile.TemporaryDirectory() as tmp:
            telemetry = Path(tmp) / "telemetry.jsonl"
            evaluator = ShadowEvaluator(
                transport=FakeTransport(RuntimeError("provider unavailable")),
                candidate_profile=PROFILE,
                telemetry_path=telemetry,
            )
            with self.assertRaises(ShadowEvaluationError):
                evaluator.evaluate(canonical_job())
            events = [json.loads(line) for line in telemetry.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events[-1]["event"], "llm_api_failure")

    def test_invalid_schema_is_rejected(self):
        llm_input = build_llm_input(canonical_job(), PROFILE)
        bad = valid_result()
        bad["evaluation_id"] = llm_input["evaluation_id"]
        bad["decision"] = "MAYBE"
        evaluator = ShadowEvaluator(transport=FakeTransport(bad), candidate_profile=PROFILE)
        with self.assertRaises(ShadowEvaluationError):
            evaluator.evaluate(canonical_job())

    def test_identical_successful_evaluation_is_reused_without_second_api_call(self):
        job = canonical_job()
        llm_input = build_llm_input(job, PROFILE)
        result = valid_result()
        result["evaluation_id"] = llm_input["evaluation_id"]
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.jsonl"
            shadow = Path(tmp) / "shadow.jsonl"
            telemetry = Path(tmp) / "telemetry.jsonl"
            transport = FakeTransport(result)
            evaluator = ShadowEvaluator(
                transport=transport,
                candidate_profile=PROFILE,
                cache_path=cache,
                shadow_path=shadow,
                telemetry_path=telemetry,
            )
            first = evaluator.evaluate(job)
            second = evaluator.evaluate(job)
            self.assertEqual(transport.calls, 1)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["cache_fingerprint"], second["cache_fingerprint"])
            events = [json.loads(line)["event"] for line in telemetry.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events[-1], "llm_evaluation_cache_hit")

    def test_changed_vacancy_text_invalidates_cache(self):
        original = canonical_job()
        changed = canonical_job(full_jd="Materially changed vacancy with mandatory clinical registration.")
        original_input = build_llm_input(original, PROFILE)
        changed_input = build_llm_input(changed, PROFILE)
        first_result = valid_result()
        first_result["evaluation_id"] = original_input["evaluation_id"]
        second_result = valid_result()
        second_result["evaluation_id"] = changed_input["evaluation_id"]
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.jsonl"
            first_transport = FakeTransport(first_result)
            ShadowEvaluator(transport=first_transport, candidate_profile=PROFILE, cache_path=cache).evaluate(original)
            second_transport = FakeTransport(second_result)
            reused = ShadowEvaluator(transport=second_transport, candidate_profile=PROFILE, cache_path=cache).evaluate(changed)
            self.assertEqual(first_transport.calls, 1)
            self.assertEqual(second_transport.calls, 1)
            self.assertFalse(reused["cache_hit"])

    def test_changed_profile_content_invalidates_cache_even_if_version_is_unchanged(self):
        job = canonical_job()
        llm_input = build_llm_input(job, PROFILE)
        result = valid_result()
        result["evaluation_id"] = llm_input["evaluation_id"]
        changed_profile = copy.deepcopy(PROFILE)
        changed_profile["guardrails"] = {"synthetic_test_change": "do not infer a new capability"}
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.jsonl"
            first_transport = FakeTransport(result)
            ShadowEvaluator(transport=first_transport, candidate_profile=PROFILE, cache_path=cache).evaluate(job)
            second_transport = FakeTransport(result)
            second = ShadowEvaluator(transport=second_transport, candidate_profile=changed_profile, cache_path=cache).evaluate(job)
            self.assertEqual(second_transport.calls, 1)
            self.assertFalse(second["cache_hit"])

    def test_changed_model_identity_invalidates_cache(self):
        job = canonical_job()
        llm_input = build_llm_input(job, PROFILE)
        result = valid_result()
        result["evaluation_id"] = llm_input["evaluation_id"]
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.jsonl"
            ShadowEvaluator(
                transport=FakeTransport(result, cache_identity="provider:model-a"),
                candidate_profile=PROFILE,
                cache_path=cache,
            ).evaluate(job)
            changed_model = FakeTransport(result, cache_identity="provider:model-b")
            second = ShadowEvaluator(
                transport=changed_model,
                candidate_profile=PROFILE,
                cache_path=cache,
            ).evaluate(job)
            self.assertEqual(changed_model.calls, 1)
            self.assertFalse(second["cache_hit"])

    def test_failed_evaluation_is_not_cached(self):
        job = canonical_job()
        llm_input = build_llm_input(job, PROFILE)
        valid = valid_result()
        valid["evaluation_id"] = llm_input["evaluation_id"]
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.jsonl"
            failing = FakeTransport(RuntimeError("temporary outage"))
            with self.assertRaises(ShadowEvaluationError):
                ShadowEvaluator(transport=failing, candidate_profile=PROFILE, cache_path=cache).evaluate(job)
            succeeding = FakeTransport(valid)
            second = ShadowEvaluator(transport=succeeding, candidate_profile=PROFILE, cache_path=cache).evaluate(job)
            self.assertEqual(succeeding.calls, 1)
            self.assertFalse(second["cache_hit"])


if __name__ == "__main__":
    unittest.main()
