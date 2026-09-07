# Phase 1 Stage 4.8: Workday Sydney pagination repair

## Scope

This stage repairs the University of Sydney Workday pagination/advertised-total contract only. It does not change UQ or Flinders pagination behavior, evaluator/scoring, query taxonomy, source coverage, global retry policy, date normalization, or unrelated collectors.

## Stage 3 defect

The frozen baseline recorded `workday_usyd` as PARTIAL with about 93 records and `repeated_page`. Shared Workday discovery uses API `offset`/`limit` pagination and treats `total` as the advertised board size. The current Sydney Workday endpoint can repeat the first result page when asked for an offset beyond its raw advertised result window.

## Fresh live diagnosis

On 2026-09-06 the live USyd endpoint advertised `total=73` on the first request. Offsets 0, 20, and 40 each returned 20 raw/parseable rows. Offset 60 returned 13 raw rows but only 12 parseable public jobs because one raw item lacked the fields required by `parse_search_payload()`. The old logic therefore had only 72 parsed IDs against advertised total 73 and requested offset 80. At offset 80 the endpoint repeated the first 20 jobs, producing the historical `repeated_page` pattern.

This shows the defect is not a public Workday job-ID collision. It is a mismatch between the raw API advertised window and the number of parseable public jobs.

## Repair

1. USyd alone now uses a source-specific discovery loop.
2. The loop advances with the same 20-row Workday API page size but determines completion from raw API positions: when `offset + raw_count >= advertised_total`, the advertised window has been fully consumed.
3. Parseable jobs are emitted as before; malformed raw rows are counted as `skipped_unparseable` in coverage rather than forcing an extra request beyond the advertised window.
4. Internal discovery deduplication uses `external_path`. The public/parser `id` contract is unchanged.
5. UQ and Flinders continue through the existing shared `paginate()` implementation unchanged.
6. Coverage now records `advertised_total`, `raw_records`, and `skipped_unparseable` for the USyd source-specific path.

## Safety boundary

This stage does not alter Workday detail extraction, record source IDs, country assignment, date normalization, retries, production caps, or evaluator logic. Global POST retry/backoff remains a later independent Stage 4 item.

## Validation boundary

Focused regressions reproduce a 73-raw/72-parseable board where offset 80 would repeat page zero and verify that discovery stops after offsets 0/20/40/60 with `complete=true`. They also lock the existing public Workday ID format and confirm Flinders still uses the old shared path. A live uncapped USyd discovery gate must complete without `repeated_page`, preserve unique external paths, and fully consume the raw advertised window. Final board-completeness certification remains a later stage.
