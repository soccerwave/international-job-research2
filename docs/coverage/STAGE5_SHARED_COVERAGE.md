# Stage 5 Shared Coverage

Version: `V0.5_SHARED_COVERAGE`

Status: **ACCEPTED**

Acceptance date: 2026-09-04

## Scope

Stage 5 implements shared and thematic discovery only:

- EURAXESS
- Academic Positions
- LinkedIn via the pinned Mads CLI
- jobs.ac.uk
- ECSS Vacancies
- dvs Stellenbörse
- FENS Job Market

Country-specific primary portals and ATS families remain Stage 6.

## Donor audit

| Source | Decision |
|---|---|
| EURAXESS | Adapt Spain production collector; remove Spain-only assumptions and discover country facets dynamically. |
| Academic Positions | Adapt Spain production collector; generalise country boards and retain stable ad IDs plus JobPosting JSON-LD. |
| LinkedIn | Adapt Spain wrapper and keep Mads' country-agnostic `linkedin-search` transport pinned to the audited commit. |
| jobs.ac.uk | No direct implementation found in audited donors; build from the Mads portal contract. |
| ECSS | No direct implementation found; build a table/PDF collector. |
| dvs | No direct implementation found; build listing plus linked-detail collector. |
| FENS | No direct implementation found; build Job Market listing/detail collector. |

No external source code from the four greenfield collectors is copied.

## Collector boundary

Collectors emit `VACANCY_SCHEMA_V1.0.0` records at `record_stage=SHARD_ENRICHED` and do not decide scientific fit. `role_family` and `role_level` remain `UNKNOWN`. A successfully retrieved Full JD is routed to review rather than being scientifically scored inside the collector. Missing detail remains fail-open as `NEEDS_DETAIL_REVIEW`. Hard blocker evaluation remains outside collectors.

## Detail strategy

Full JD retrieval remains source-local:

- EURAXESS: detail HTML.
- Academic Positions: JobPosting JSON-LD with HTML fallback.
- LinkedIn: pinned Mads `detail` command.
- jobs.ac.uk: detail HTML.
- ECSS: linked vacancy PDF/HTML.
- dvs: linked vacancy PDF/HTML.
- FENS: Job Market detail HTML.

PDF extraction uses `pypdf`. Detail failures remain fail-open.

## Acceptance fixes

### EURAXESS

The initial international adaptation incorrectly relied on a legacy country facet assumption and could silently fall back to global results. Live investigation established the current EURAXESS form contract: country options expose numeric `job_country[]` values and the applied form resolves to stable GET facets such as `f[0]=job_country:794` for Germany together with `f[1]=offer_type:job_offer`.

The production collector now discovers the current country option values, constructs the stable GET facet, stores the requested country/facet per record, and has no silent global fallback. Generic detail headings such as `Job offer` no longer replace the actual listing title.

### dvs

The thematic board itself is not treated as proof that every vacancy is German. Country is populated only from explicit source-local evidence such as `.de`, `.at`, `.ch`, Germany, Austria, Switzerland, Wien/Vienna, or equivalent text. Unknown remains null and fail-open.

### FENS

Live detail inspection confirmed that country metadata is present in the page text. Country names are preserved even when outside target markets. Hong Kong is normalized to ISO code `HK`; its market tier remains `UNKNOWN`, so metadata preservation does not expand the configured market scope. Empty department fields remain empty rather than absorbing the following Description field.

## Final live acceptance

GitHub Actions run: `33895687778`

Validated commit: `f6d622c85d9d3288df2aaff2d141d8b6c2c72c7a`

Validation profile: `STAGE5_FINAL_SHARED_COVERAGE`

Both the Stage 5 parser/schema tests and the Stage 4 regression suite completed successfully. The live-smoke job also completed successfully.

| Source | Live discovery | Full JD | Country check |
|---|---|---|---|
| EURAXESS | PASS | FULL | `DE`, strictly requested Germany |
| Academic Positions | PASS | FULL | `DE` |
| jobs.ac.uk | PASS | FULL | `GB` |
| ECSS | PASS | FULL | Source-provided country present (`NO` in acceptance sample) |
| dvs | PASS | FULL | Explicit evidence resolved `DE` in acceptance sample |
| FENS | PASS | FULL | Source-provided country normalized to `HK` in acceptance sample |
| LinkedIn / Mads | PASS | FULL | `DE`, strictly requested Germany |

The thematic smoke samples are transport tests, not fit decisions. An out-of-scope country or an unsuitable scientific role in a smoke sample does not imply inclusion in final recommendations; Stage 7 policy/evaluation will decide fit.

## Freeze boundary

Stage 5 freezes the shared-source transport baseline and source registry. It does **not** implement:

- Stage 6 country-primary portals and ATS coverage,
- cross-source canonical identity/deduplication,
- the Stage 7 international scientific evaluator,
- persistent NEW/SEEN/changed/reopened state,
- R2 persistence,
- Excel/Telegram reporting,
- production scheduling.
