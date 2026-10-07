from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.llm.experiment_evidence import R2ExperimentEvidenceStore, build_experiment_evidence_bundle
from src.llm.full_evaluation_routing import FullEvaluationRecord, ORIGIN_LLM_RESCUE, ORIGIN_MAIN
from src.llm.openai_transport import OpenAIChatCompletionsTransport, OpenAITransportConfig
from src.llm.r2_evaluation_cache import R2EvaluationCacheStore
from src.llm.rescue_triage import PASS_TO_FULL_REVIEW, RescueTriageEvaluator
from src.llm.shadow_evaluator import ShadowEvaluator
from src.state.r2_store import R2StateStore

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "config" / "llm_candidate_profile_v1.json"
MODEL = "gpt-6-luna"
SMOKE_CACHE_KEY = "llm/cache/smoke-evaluations-v0.1.jsonl"


def representative_jobs() -> list[dict]:
    return [
        {
            "canonical_id": "smoke-main-exercise-neuroscience",
            "source_record_id": "smoke:main:exercise-neuroscience",
            "source": {
                "source_key": "smoke",
                "detail_url": "https://example.org/smoke/main",
                "source_status": "OPEN",
            },
            "position": {
                "title_raw": "Postdoctoral Research Fellow in Exercise Neuroscience",
                "institution_raw": "Example University",
                "department": "Department of Neuroscience",
                "role_family": "RESEARCH",
                "role_level": "POSTDOC",
                "employment_type": "FULL_TIME",
            },
            "location": {
                "city": "Barcelona",
                "country_code": "ES",
                "country_name": "Spain",
            },
            "contract": {"term_type": "FIXED_TERM"},
            "description": {
                "detail_status": "FULL",
                "full_jd": (
                    "The successful candidate will conduct human research examining how aerobic exercise "
                    "and physical activity influence stress regulation, cognition and brain health. "
                    "Responsibilities include participant recruitment, supervised exercise interventions, "
                    "analysis of behavioral and physiological data, collaboration on MRI-related research, "
                    "manuscript preparation and conference dissemination. A PhD in exercise science, "
                    "neuroscience, psychology, physiology or a closely related field is required. Experience "
                    "with randomized interventions, stress physiology, cognition or neuroimaging is desirable. "
                    "The post is a full-time fixed-term postdoctoral research appointment."
                ),
            },
            "requirements": {},
            "raw_extra": {
                "evaluation": {
                    "recommendation": "APPLY",
                    "evaluator_version": "SMOKE_RULE_V1",
                }
            },
        },
        {
            "canonical_id": "smoke-rescue-behavioral-medicine",
            "source_record_id": "smoke:rescue:behavioral-medicine",
            "source": {
                "source_key": "smoke",
                "detail_url": "https://example.org/smoke/rescue",
                "source_status": "OPEN",
            },
            "position": {
                "title_raw": "Research Fellow in Behavioral Medicine and Stress Resilience",
                "institution_raw": "Example Health Institute",
                "department": "Behavioral Health Research Unit",
                "role_family": "RESEARCH",
                "role_level": "POSTDOC",
                "employment_type": "FULL_TIME",
            },
            "location": {
                "city": "London",
                "country_code": "GB",
                "country_name": "United Kingdom",
            },
            "contract": {"term_type": "FIXED_TERM"},
            "description": {
                "detail_status": "FULL",
                "full_jd": (
                    "This interdisciplinary research fellowship investigates behavioral and physiological "
                    "determinants of resilience to psychosocial stress. The fellow will contribute to human "
                    "cohort and intervention studies, collect psychological and autonomic measures, analyze "
                    "longitudinal data and collaborate across behavioral medicine, public health and neuroscience. "
                    "Applicants should hold a PhD in a relevant health, behavioral or biomedical discipline. "
                    "Experience with physical activity, lifestyle interventions, stress research, wearable "
                    "physiology or mental health outcomes is welcomed but not mandatory."
                ),
            },
            "requirements": {},
            "raw_extra": {
                "evaluation": {
                    "recommendation": "SKIP",
                    "evaluator_version": "SMOKE_RULE_V1",
                }
            },
        },
    ]


def main() -> int:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is missing")

    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile_version = str(profile.get("profile_version") or "").strip()
    jobs = representative_jobs()

    transport = OpenAIChatCompletionsTransport(
        OpenAITransportConfig(
            api_key=api_key,
            model=MODEL,
            base_url="https://api.openai.com/v1",
        )
    )
    state_store = R2StateStore.from_env()
    durable_cache = R2EvaluationCacheStore(state_store, relative_key=SMOKE_CACHE_KEY)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache_path = root / "smoke-cache.jsonl"
        first_loaded = durable_cache.hydrate(cache_path)

        triage_evaluator = RescueTriageEvaluator(
            transport=transport,
            candidate_profile=profile,
            cache_path=cache_path,
        )
        full_evaluator = ShadowEvaluator(
            transport=transport,
            candidate_profile=profile,
            cache_path=cache_path,
        )

        rescue_triage = triage_evaluator.evaluate(jobs[1])
        main_eval = full_evaluator.evaluate(jobs[0])
        rescue_eval = full_evaluator.evaluate(jobs[1])

        if not main_eval.get("llm_result"):
            raise RuntimeError("MAIN full evaluation returned no llm_result")
        if not rescue_eval.get("llm_result"):
            raise RuntimeError("Rescue full evaluation returned no llm_result")
        if not rescue_triage.get("llm_result"):
            raise RuntimeError("Rescue triage returned no llm_result")

        synced = durable_cache.sync(cache_path, expected_etag=first_loaded.etag)

        # Prove cross-hydration reuse, not merely in-memory reuse.
        rehydrated_path = root / "rehydrated-cache.jsonl"
        second_loaded = durable_cache.hydrate(rehydrated_path)
        if not second_loaded.exists:
            raise RuntimeError("durable smoke cache did not exist after sync")

        triage_again = RescueTriageEvaluator(
            transport=transport,
            candidate_profile=profile,
            cache_path=rehydrated_path,
        ).evaluate(jobs[1])
        full_again = ShadowEvaluator(
            transport=transport,
            candidate_profile=profile,
            cache_path=rehydrated_path,
        ).evaluate(jobs[0])

        if triage_again.get("cache_hit") is not True:
            raise RuntimeError("rehydrated Rescue triage was not a cache hit")
        if full_again.get("cache_hit") is not True:
            raise RuntimeError("rehydrated Full evaluation was not a cache hit")

        full_records = [
            FullEvaluationRecord(
                job_id=jobs[0]["canonical_id"],
                origin=ORIGIN_MAIN,
                triage_id=None,
                evaluation=main_eval,
            ),
            FullEvaluationRecord(
                job_id=jobs[1]["canonical_id"],
                origin=ORIGIN_LLM_RESCUE,
                triage_id=rescue_triage.get("triage_id"),
                evaluation=rescue_eval,
            ),
        ]

        run_id = f"smoke-{os.getenv('GITHUB_RUN_ID', 'local')}-{os.getenv('GITHUB_RUN_ATTEMPT', '1')}"
        run_date = datetime.now(timezone.utc).date().isoformat()
        bundle = build_experiment_evidence_bundle(
            run_id=run_id,
            run_date=run_date,
            model=MODEL,
            candidate_profile_version=profile_version,
            canonical_jobs=jobs,
            full_evaluation_records=full_records,
            rescue_triage_records=[rescue_triage],
            disagreement_rows=[],
            failures=[],
            extra_summary={
                "smoke_test": True,
                "cache_rehydration_verified": True,
            },
        )
        evidence_store = R2ExperimentEvidenceStore(state_store, prefix="llm/smoke-tests")
        persisted = evidence_store.persist(bundle)

        summary = {
            "status": "PASS",
            "model": MODEL,
            "profile_version": profile_version,
            "triage_decision": (rescue_triage.get("llm_result") or {}).get("decision"),
            "main_full_decision": (main_eval.get("llm_result") or {}).get("decision"),
            "rescue_full_decision": (rescue_eval.get("llm_result") or {}).get("decision"),
            "first_pass": {
                "triage_cache_hit": rescue_triage.get("cache_hit"),
                "main_cache_hit": main_eval.get("cache_hit"),
                "rescue_full_cache_hit": rescue_eval.get("cache_hit"),
            },
            "rehydrated_cache": {
                "triage_cache_hit": triage_again.get("cache_hit"),
                "full_cache_hit": full_again.get("cache_hit"),
            },
            "tokens": {
                "triage_input": rescue_triage.get("input_tokens"),
                "triage_output": rescue_triage.get("output_tokens"),
                "main_input": main_eval.get("input_tokens"),
                "main_output": main_eval.get("output_tokens"),
                "rescue_input": rescue_eval.get("input_tokens"),
                "rescue_output": rescue_eval.get("output_tokens"),
            },
            "durable_cache": {
                "key": synced.get("key"),
                "sha256": synced.get("sha256"),
                "bytes": synced.get("bytes"),
            },
            "durable_evidence": {
                "key": persisted.key,
                "sha256": persisted.sha256,
                "bytes": persisted.bytes,
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
