from __future__ import annotations

import json
import unittest
from io import BytesIO

from src.llm.experiment_evidence import (
    ExperimentEvidenceError,
    R2ExperimentEvidenceStore,
    build_experiment_evidence_bundle,
    serialize_experiment_evidence,
)
from src.llm.full_evaluation_routing import FullEvaluationRecord
from src.state.r2_store import R2StateStore


def job(job_id: str, recommendation: str) -> dict:
    return {
        "canonical_id": job_id,
        "source": {"detail_url": f"https://example.org/{job_id}"},
        "position": {
            "title_raw": f"Job {job_id}",
            "institution_raw": "Example University",
        },
        "location": {"country_code": "ES", "country_name": "Spain"},
        "description": {
            "detail_status": "FULL",
            "full_jd": f"Secret full JD content for {job_id}",
        },
        "raw_extra": {
            "evaluation": {
                "recommendation": recommendation,
                "evaluator_version": "RULE_TEST_V1",
            }
        },
    }


def full(job_id: str, origin: str, decision: str, *, cache_hit: bool, input_tokens: int) -> FullEvaluationRecord:
    return FullEvaluationRecord(
        job_id=job_id,
        origin=origin,
        triage_id=f"triage-{job_id}" if origin == "LLM_RESCUE" else None,
        evaluation={
            "evaluation_id": f"eval-{job_id}",
            "cache_hit": cache_hit,
            "cache_fingerprint": f"fp-{job_id}",
            "model": "gpt-6-luna",
            "input_tokens": input_tokens,
            "output_tokens": 50,
            "latency_ms": 20,
            "evaluated_at": "2026-10-07T00:00:00+00:00",
            "llm_result": {
                "decision": decision,
                "fit_score": 80,
                "confidence": 90,
                "evidence_quality": "FULL_JD",
                "hard_blocker": False,
                "hard_blocker_reason": None,
                "reason_short": "Relevant role.",
            },
        },
    )


def triage(job_id: str, decision: str, *, cache_hit: bool = False) -> dict:
    return {
        "job_id": job_id,
        "triage_id": f"triage-{job_id}",
        "cache_hit": cache_hit,
        "cache_fingerprint": f"triage-fp-{job_id}",
        "model": "gpt-6-luna",
        "input_tokens": 120,
        "output_tokens": 20,
        "latency_ms": 5,
        "evaluated_at": "2026-10-07T00:00:00+00:00",
        "llm_result": {
            "decision": decision,
            "reason_short": "Metadata routing.",
        },
    }


class FakeS3Error(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeR2Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[dict] = []

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if key in self.objects and kwargs.get("custom_headers") == {"If-None-Match": "*"}:
            raise FakeS3Error("PreconditionFailed")
        payload = bytes(kwargs["Body"])
        self.objects[key] = payload
        self.put_calls.append(kwargs)
        return {"ETag": '"etag-new"'}

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise FakeS3Error("NoSuchKey")
        return {"Body": BytesIO(self.objects[Key]), "ETag": '"etag-new"', "Metadata": {}}


class LLMExperimentEvidenceL73Tests(unittest.TestCase):
    def _bundle(self):
        jobs = [
            job("main-1", "APPLY"),
            job("rescue-1", "SKIP"),
            job("rescue-reject", "SKIP"),
        ]
        return build_experiment_evidence_bundle(
            run_id="github-123",
            run_date="2026-10-07",
            model="gpt-6-luna",
            candidate_profile_version="LLM_CANDIDATE_PROFILE_V1.1.0",
            canonical_jobs=jobs,
            full_evaluation_records=[
                full("main-1", "MAIN", "APPLY", cache_hit=True, input_tokens=1000),
                full("rescue-1", "LLM_RESCUE", "REVIEW", cache_hit=False, input_tokens=2000),
            ],
            rescue_triage_records=[
                triage("rescue-1", "PASS_TO_FULL_REVIEW", cache_hit=False),
                triage("rescue-reject", "CLEARLY_OUT_OF_SCOPE", cache_hit=True),
            ],
            disagreement_rows=[
                {
                    "job_id": "main-1",
                    "rule_recommendation": "APPLY",
                    "llm_decision": "APPLY",
                    "is_disagreement": False,
                }
            ],
            failures=[
                {"job_id": "broken", "origin": "MAIN", "error": "synthetic"},
            ],
            created_at="2026-10-07T00:00:00+00:00",
        )

    def test_bundle_preserves_main_rescue_triage_and_metrics(self):
        bundle = self._bundle()
        self.assertEqual(len(bundle["main_evaluations"]), 1)
        self.assertEqual(len(bundle["rescue_full_evaluations"]), 1)
        self.assertEqual(len(bundle["rescue_triage"]), 2)
        self.assertEqual(bundle["main_evaluations"][0]["rule_recommendation"], "APPLY")
        self.assertEqual(bundle["rescue_full_evaluations"][0]["llm_decision"], "REVIEW")
        self.assertEqual(bundle["summary"]["cache_hits"], 2)
        self.assertEqual(bundle["summary"]["api_calls"], 2)
        self.assertEqual(bundle["summary"]["input_tokens"], 3240)
        self.assertEqual(bundle["summary"]["output_tokens"], 140)
        self.assertEqual(bundle["summary"]["failures"], 1)

    def test_full_jd_is_not_duplicated_but_hash_is_stored(self):
        payload = serialize_experiment_evidence(self._bundle()).decode("utf-8")
        self.assertNotIn("Secret full JD content", payload)
        decoded = json.loads(payload)
        self.assertTrue(decoded["main_evaluations"][0]["full_jd_sha256"])

    def test_evidence_is_immutable_per_run_in_r2(self):
        client = FakeR2Client()
        store = R2ExperimentEvidenceStore(R2StateStore(client, "bucket"))
        bundle = self._bundle()
        first = store.persist(bundle)
        self.assertEqual(
            first.key,
            "llm/experiments/2026-10-07/github-123/evidence.json",
        )
        self.assertEqual(client.put_calls[0]["custom_headers"], {"If-None-Match": "*"})
        with self.assertRaises(ExperimentEvidenceError):
            store.persist(bundle)

    def test_different_run_ids_create_separate_objects(self):
        client = FakeR2Client()
        store = R2ExperimentEvidenceStore(R2StateStore(client, "bucket"))
        first = self._bundle()
        second = dict(first)
        second["run_id"] = "github-124"
        store.persist(first)
        store.persist(second)
        self.assertEqual(len(client.objects), 2)

    def test_missing_canonical_job_for_full_evaluation_is_rejected(self):
        with self.assertRaises(ExperimentEvidenceError):
            build_experiment_evidence_bundle(
                run_id="x",
                run_date="2026-10-07",
                model="gpt-6-luna",
                candidate_profile_version="P1",
                canonical_jobs=[],
                full_evaluation_records=[
                    full("missing", "MAIN", "APPLY", cache_hit=False, input_tokens=1),
                ],
                rescue_triage_records=[],
                disagreement_rows=[],
                failures=[],
            )


if __name__ == "__main__":
    unittest.main()
