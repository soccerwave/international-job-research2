# Phase 1 Stage 4.3: LinkedIn durability

## Scope

This stage adds durability only. It does not change LinkedIn query taxonomy, country coverage, pagination policy, limits, subprocess timeout, detail-enrichment policy, sharding, evaluator behavior, scoring, or report delivery.

Stage 4.2 made LinkedIn progress observable. Stage 4.3 makes completed units of that work survive ordinary failure or cancellation when the GitHub runner reaches the existing `if: always()` LinkedIn diagnostics upload step.

## Checkpoint layout

Production LinkedIn shards write checkpoint files below the existing diagnostics artifact path:

`artifacts/<run-id>/diagnostics/<shard-id>/checkpoints/`

The files are:

- `discovery.jsonl`: one append-only event after each completed search page. Each event records country, query, page, and the listing objects returned by that completed page.
- `records.jsonl`: one append-only event after each canonical LinkedIn record is built, including completed detail data or a recorded detail-fetch failure.
- `state.json`: an atomically replaced summary of the latest completed stage, page/record counts, and last completed job ID where applicable.

Each append is flushed immediately. `state.json` is written via a temporary file and atomic replace so an interrupted write does not expose a half-written JSON document.

## Cancellation boundary

The checkpoint does not make an in-flight request magically recoverable. If cancellation occurs during page N, only pages completed before page N are guaranteed to be present. If cancellation occurs during detail record N, only records completed before N are guaranteed to be present.

The existing production workflow already uploads the complete LinkedIn diagnostics directory with `if: always()`, so checkpoint files require no new production workflow step. As with Stage 4.2 diagnostics, force termination, runner loss, or a platform-level cancellation that prevents later steps from running can still prevent artifact upload.

## Explicit non-goals

This is not a resume engine. A future run does not read these checkpoint files and does not skip previously completed pages or details. The files are recovery evidence and durable partial job data only. Resume/restart semantics, performance redesign, sharding, concurrency, and query taxonomy remain separate decisions.

## Acceptance criteria

Stage 4.3 passes only if focused regressions prove that:

1. a completed discovery page remains on disk after an interruption on a later page;
2. a completed canonical record remains on disk after an interruption during a later detail request;
3. a successful run ends with `state.json` marked `COMPLETE`;
4. enabling checkpointing does not change normal collector output;
5. a bounded live run using the pinned Mads transport creates discovery, record, and state checkpoint files.
