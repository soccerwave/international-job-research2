# L6.1 — LLM Evaluation Cache / Idempotency

Status: IMPLEMENTED ON L6.1 BRANCH

## Purpose

Avoid paying to re-evaluate the same effective LLM request on later runs.

This is a cost/idempotency patch only. It does not change LLM authority, rule-based authority, sampling policy, or the roadmap after L6.

## Reuse rule

A prior successful result is reused only when the versioned cache fingerprint is identical.

The fingerprint binds:

- the complete LLM input for the vacancy, including Full JD and structured supporting fields;
- the complete candidate profile content and profile version;
- the evaluator system prompt;
- the structured output schema;
- the configured provider/model transport identity;
- the cache fingerprint version.

Therefore a changed vacancy, profile, prompt/schema, or model produces a cache miss and a fresh LLM call.

## Failure policy

Only successfully validated LLM results are written to the cache.

API failures, malformed JSON, schema-invalid outputs, and interrupted evaluations are not cached as successful results and will be retried on a later run.

## Daily shadow output

A cache hit is still written to the current shadow-output JSONL so downstream L5 comparison can see the sampled job for that run. The reused row is marked with `cache_hit=true` and `cache_reused_at` while preserving the original `evaluated_at`.

Telemetry emits `llm_evaluation_cache_hit` instead of an API-start/store pair for reused evaluations.

## Persistence

`run_llm_shadow.py` accepts `--cache-path` or `LLM_SHADOW_CACHE_PATH`.

If neither is provided, the runner uses `llm_evaluation_cache.jsonl` beside the shadow-output file. For real multi-day production use, the cache path must point to storage that persists across runs. Durable production wiring is intentionally separate from this patch.

## Non-goals

L6.1 does not:

- change L4 sampling;
- alter the candidate profile;
- expose rule-based decisions to the LLM;
- change production recommendations;
- promote or remove jobs;
- implement L7 benchmark construction.
