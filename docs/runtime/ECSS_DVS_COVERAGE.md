# Phase 1 Stage 4.13: ECSS and DVS coverage events

## Scope

This stage adds explicit collection-coverage evidence to the ECSS and DVS thematic collectors. It does not change query taxonomy, evaluator/scoring, global pagination behavior, retry/backoff, date normalization, Full-JD semantics, or source coverage.

Both boards are collected as single listing pages. Before this stage they could return records without emitting any coverage event, so production diagnostics could not distinguish an explicitly complete collection from a collector with no coverage evidence.

## Contract

For each successful listing fetch and parse, each collector now emits exactly one coverage event through `record_coverage`.

- `stop_reason=single_page_complete`, `complete=true`: the whole parsed single page was retained.
- `stop_reason=configured_record_limit`, `complete=false`: an explicit `max_jobs` diagnostic limit truncated parsed records.

Each event includes:

- `pages=1`
- `records`: records retained for the run
- `discovered_records`: records parsed from the listing page before the optional limit
- `configured_record_limit`

An empty but successfully fetched and parsed page is represented explicitly as `single_page_complete` with zero records. Transport failures still raise and are reported by the production shard as source errors; this stage does not alter failure/retry behavior.

## Production semantics

Production passes `max_jobs=None`, so a successful ECSS or DVS listing fetch is expected to emit `single_page_complete`. The existing production shard runtime already captures coverage events and marks any `complete=false` event as PARTIAL.

## Validation

Focused regressions verify uncapped complete events, bounded truncation events, counts, and explicit zero-record completion for both collectors. The dedicated live workflow fetches both real boards uncapped with detail enrichment disabled and requires exactly one complete `single_page_complete` event per source.

Full-board content recall certification remains a later stage; this change certifies observability semantics, not that the boards themselves expose every relevant vacancy.
