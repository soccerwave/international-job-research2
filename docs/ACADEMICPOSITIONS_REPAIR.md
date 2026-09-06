# Phase 1 Stage 4.5: AcademicPositions repair

## Scope

This stage repairs AcademicPositions only. It does not change country scope, evaluator logic, scoring, source expansion, or unrelated collectors.

## Baseline defects

The frozen Phase 1 baseline showed AcademicPositions as PARTIAL with multiple country/page HTTP 404 failures and 159 full descriptions unavailable. The previous collector generated `?page=N` requests until an empty page or HTTP failure, without consulting the site's paginator. It also used the stale Czech slug `czech-republic`.

## Fresh live evidence

On 2026-09-06, the current Academic Positions site showed:

- Germany country pages are live and expose a finite paginator.
- Czechia now uses `/jobs/country/czechia`, not `/jobs/country/czech-republic`.
- The Ireland country route can return HTTP 404 when there is no active country result page.
- Live AcademicPositions detail pages remain directly accessible and contain substantial vacancy text.

The post-repair GitHub Actions gate then exercised the collector on a fresh runner:

- Run: `34043566081`
- Artifact: `9992409241`
- Artifact digest: `sha256:a17514634633d437bfe24aeba7b4732e01a8f8166947907290725cbc7dd18142`
- Germany uncapped discovery: 56 records across 2 pages
- Germany terminal evidence: `last_page`
- Germany coverage: `complete=true`
- Germany live `advertised_total`: `null`; completion was therefore proven by the site's paginator, not by an advertised count
- Bounded production SourceCall: 3 records
- Detail attempts: 3
- Useful details: 3
- Detail statuses: `FULL`, `FULL`, `FULL`

## Repair

1. `CZ` now maps to `czechia`.
2. Each country page reads the advertised job count when present.
3. Each page inspects the actual same-origin paginator and returns `has_next` to the shared pagination contract.
4. A first-page 404 on a configured country route is treated as a clean zero-current-jobs result. A later-page HTTP failure remains incomplete/partial because it contradicts the prior paginator state.
5. Detail fallback prefers `main`/`article` text before whole-page text when JSON-LD does not provide a sufficiently long description.

## Safety properties

- Production remains uncapped when `max_jobs=None` and `max_pages_per_country=None`.
- A real later-page request failure remains PARTIAL and preserves earlier rows.
- Country failures do not starve later countries.
- No new countries or sources are added.

## Certification boundary

Stage 4.5 validates repaired pagination termination, current Czech country routing, bounded production wiring, and a fresh detail sample. It does not claim that all 159 historical unavailable descriptions are recovered, nor final board-completeness certification across every configured country. Those claims require the later fresh full production and board-completeness stages.
