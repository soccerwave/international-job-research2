# Phase 1 Stage 4.7: PageUp Monash pagination repair

## Scope

This stage repairs the Monash PageUp pagination contract only. It does not change Deakin or UNSW pagination behavior, evaluator/scoring, source coverage, query taxonomy, Workday, or any unrelated collector.

## Stage 3 defect

The frozen baseline recorded `pageup_monash` as PARTIAL with 80 records and `repeated_page`. The shared generic next-link parser accepts labels such as `More Jobs`; on PageUp this is unsafe because a generic `More Jobs` navigation link can point back to the listing root/self instead of a strictly forward result page.

## Fresh live evidence

On 2026-09-06 the current Monash PageUp board uses explicit forward listing URLs such as:

- `?page=2&page-items=20`
- `?page=3&page-items=20`
- `?page=4&page-items=20`

The terminal current page has no forward `More Jobs` link. This gives a source-specific invariant: valid Monash pagination must remain on the same listing origin/path and must contain an explicit numeric `page` strictly greater than the current page.

## Repair

1. Monash now uses a source-specific `monash_next_listing_url()` parser.
2. A next link is accepted only if it remains on the same listing origin/path and advances to a larger explicit page number.
3. Root, self, backward, fragment, JavaScript, and cross-path `More Jobs` links are ignored.
4. Monash uses this strict parser inside a small source-specific pagination loop backed by the existing shared `paginate()` coverage contract.
5. Deakin and UNSW continue through the existing generic `html_pages()` path unchanged.

## Safety boundary

The repair does not alter Monash job parsing, detail enrichment, country assignment, record schema, evaluator logic, or production caps. Production remains uncapped when `max_jobs=None`.

## Validation boundary

Focused regressions recreate the historical root/self-loop failure and verify a clean `last_page` stop. A live uncapped Monash discovery probe must finish with `complete=true`, `stop_reason=last_page`, multiple pages, and unique job IDs. Final board-completeness certification remains a later stage.
