# L6.1 — Durable LLM Evaluation Cache

Status: IMPLEMENTED ON BRANCH

Purpose: preserve successful semantic LLM evaluations across runs so unchanged vacancies are not charged again.

## Storage boundary

The cache is stored in a separate Cloudflare R2 object and is not embedded in authoritative production job state.

Default relative key:

`llm/cache/evaluations-v0.1.jsonl`

Override with `LLM_R2_CACHE_KEY`.

## Runtime behavior

`run_llm_shadow.py --r2-cache` (or `LLM_R2_CACHE_ENABLED=true`) performs:

1. one R2 GET before evaluation to hydrate the local successful-evaluation cache;
2. normal LLM evaluation with fingerprint reuse from L6.1;
3. one conditional R2 PUT after the run only when the local cache changed.

If the cache did not change, no R2 write is performed.

## Safety

- the object carries SHA-256 metadata and is verified on read;
- first creation uses `If-None-Match: *`;
- updates use `If-Match: <hydrated-etag>`;
- stale concurrent writers fail explicitly rather than silently overwriting a newer cache;
- failed/malformed LLM evaluations are never successful cache entries;
- changing vacancy context, candidate profile, prompt/schema, or model identity still forces a new API evaluation.

The implementation reuses the repository's existing R2 credentials/client configuration. No new GitHub Action or storage system is introduced.

## Scope

This patch provides durable cache storage for the shadow evaluator runner. It does not yet place the LLM evaluator into `production.yml`, change rule-based authority, or begin L7 Gold Benchmark.
