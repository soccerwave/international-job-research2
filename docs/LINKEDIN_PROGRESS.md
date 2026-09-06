# Phase 1 Stage 4.2: LinkedIn observability

## Scope

This stage changes observability only. It does not change LinkedIn query taxonomy, country coverage, pagination policy, limits, subprocess timeout, detail-enrichment policy, sharding, evaluator behavior, scoring, or report delivery.

## Evidence that motivated the change

Production run 34029865296 started LinkedIn Europe collection at 11:18:59 UTC and was canceled at 12:06:47 UTC after 47m48s. The previous implementation captured the Mads CLI subprocess output and emitted no intermediate collection progress, so the log could not establish the active country, query, page, job ID, or request state at cancellation.

LinkedIn Australia in the same run completed after roughly 12m54s with 1,407 unique listings and a terminal lecturer-search HTTP 400 after 100 pages. That proved the collector could spend substantial time in serial discovery/detail work, but did not identify Europe's exact bottleneck.

## Instrumentation

The collector now emits flushed JSON diagnostics to stderr for:

- collection start;
- each search request start, completion, terminal error, and 30-second waiting heartbeat;
- each search page result with country, query, page, returned rows, and query-level unique count;
- query completion or query failure;
- discovery completion with page count and failure count;
- each detail request start, completion, terminal error, and heartbeat with job ID and index/total;
- each detail result status;
- final collection summary with separate discovery/detail durations and failure counts.

No job-description body is included in progress events.

For production LinkedIn shards, the entrypoint writes each event immediately to:

`artifacts/<run-id>/diagnostics/<shard-id>/progress.jsonl`

The production workflow uploads this directory as a separate LinkedIn diagnostics artifact with `if: always()`. This preserves available diagnostics on normal failure or cancellation when the runner reaches the upload step. Force termination or runner loss can still prevent artifact upload. The GitHub Actions log remains the primary live visibility surface because every event is flushed immediately.

## Certification boundary

Stage 4.2 certifies observability, not speed or recall. A bounded live probe verifies that the pinned Mads transport produces real search events with exact country/query/page coordinates. Performance redesign, further sharding, query taxonomy, pagination strategy, and recall certification remain later stages.
