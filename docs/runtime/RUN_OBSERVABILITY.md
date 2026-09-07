# Phase 1 Stage 5.1: Production run-level observability

## Scope

Stage 5.1 adds a read-only run-level observability view over the immutable production shard artifacts that already exist. It does not change collector behavior, source coverage, query taxonomy, pagination, retry/backoff, evaluator/scoring, Full-JD semantics, date normalization, state semantics, or finalizer acceptance policy.

This stage also does not implement stall/heartbeat detection, failure taxonomy, interrupted-run durability, or runtime anomaly thresholds. Those remain later Stage 5 slices.

## Problem

Before Stage 5.1, each production shard already recorded timing and `source_results`, but the authoritative finalizer summary did not expose a single run-level view of those facts. In particular, source-level `elapsed_ms` and the runtime shard instances behind a logical source were not retained in the final production summary.

That made questions such as these harder than necessary to answer after a run:

- Which shard took the longest?
- Which source inside a shard consumed the time?
- How many records and detail fetches did each shard emit?
- Which warning/error belonged to which shard or logical source?
- Which expected shard artifact was missing?
- Did an unexpected shard artifact appear?
- For a logical source split across multiple runtime shards, which instances contributed to the aggregate?

## Implementation

`src/runtime/observability.py` introduces `collect_run_observability()`.

It verifies immutable shard bundles and produces:

### Per-shard rows

- shard id
- status
- source ids
- start and finish timestamps
- elapsed milliseconds
- records observed and emitted
- detail attempted and succeeded
- warning/error counts and messages

Expected shards without an artifact are represented explicitly as `MISSING` with `MISSING_SHARD_ARTIFACT`. Unexpected shard artifacts are surfaced separately. Absence is never interpreted as healthy execution.

### Per-logical-source rows

Source results are aggregated by `report_key`/logical source while retaining an `instances` list containing:

- runtime shard id
- source id
- report key
- status
- records
- elapsed milliseconds
- warning count
- error

This preserves the runtime topology for sources such as LinkedIn Europe, where one logical source is intentionally partitioned across multiple GitHub matrix shards.

### Run totals

The summary exposes totals for records, detail attempts/successes, shard/source elapsed sums, warnings, and errors, plus shard/source status counts.

## Authoritative finalizer wiring

`scripts/run_production_finalizer.py` now attaches the read-only result under:

`run_observability`

and persists that enriched object in `production/<run-id>/production_summary.json` for normal, partial, and strict-preflight-failed finalizer outcomes that return a result.

The observability view is descriptive. It does not change whether a run is accepted or rejected and does not mutate authoritative state.

## Validation

Initial Stage 5.1 validation run: `34052169501`.

Artifact: `9994872973`.

Artifact digest: `sha256:05aff9a55d0bd4047879df99ebe5c11c4d6888e78e7f8faa91433b9591bbb9a5`.

A bounded real production shard probe ran `thematic` with `PRODUCTION_MAX_JOBS_PER_SOURCE=1` and produced:

- shard elapsed: 7,792 ms
- records observed/emitted: 3 / 3
- detail attempted/succeeded: 3 / 3
- `ecss`: 1 record, 3,130 ms
- `dvs`: 1 record, 1,666 ms
- `fens`: 1 record, 2,994 ms
- missing shards: none for the one-shard probe
- unexpected shards: none

All three sources were correctly reported as `PARTIAL` because the bounded diagnostic limit intentionally produced `configured_record_limit` coverage warnings. This demonstrates that the run view preserves both timing and the reason a source is degraded.

Focused regressions cover multi-shard logical-source aggregation, explicit missing shards, unexpected shards, warning/error/timing preservation, run totals, and finalizer persistence into `production_summary.json`.

## Certification boundary

Stage 5.1 certifies the run-level aggregation and finalizer wiring. It does not certify full uncapped production runtime, stall detection, operational alerting, full board completeness, or recall.
