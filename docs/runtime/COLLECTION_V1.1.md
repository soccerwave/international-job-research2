# Production collection V1.1

Date: 2026-09-06. Base: `5e8f39455f7d8a27136a37c66cd64a565fcfee91`.

## Behavior

Production defaults to `PRODUCTION_MAX_JOBS_PER_SOURCE=all`. No record or page
cap is applied by the production source map. An explicit positive integer remains
available for diagnostic runs. Scheduled runs do not inherit the old repository
variable that could silently restore the 20-record limit. Workflow dispatch defaults
to `all`; callers explicitly sending a positive integer still request a limited run.

Workday uses 20 records per request and advances the offset. SmartRecruiters uses
100 per request; University Vacancies uses its page parameter. LinkedIn uses the
pinned donor's supported `--page` option and omits its client-side `--limit` slice.
The existing 14-day LinkedIn freshness window and existing queries remain unchanged.
EURAXESS, AcademicPositions, jobs.ac.uk and FENS paginate without a production page
cap. Each country/query has its own pagination history, so cross-query duplicate
records do not prematurely stop a new query's second page.

PageUp, SuccessFactors, CoreHR and generic HTML portals follow same-origin next-page
links. This is not a claim to support every JavaScript/form-based paginator: detected
unsupported dynamic pagination is recorded as incomplete. ECSS/dvs read all parsed
items on their existing listing pages. Parsers and upstream availability still limit
coverage; removing a cap does not prove market completeness.

Empty/last pages and advertised totals terminate successful pagination. Repeated
IDs/URLs and later-page failures stop traversal and retain earlier records, with
incomplete coverage diagnostics. Records, pages, advertised totals, stop reasons
and errors are stored in shard source results. Failed detail retrieval also marks
source health PARTIAL. No absence is interpreted as vacancy closure.

The workflow timeout is 360 minutes per shard (previously 60), a platform execution
ceiling rather than a desired duration. A hard runner cancellation cannot checkpoint
in-memory rows: a missing bundle remains a missing shard in the existing finalizer.
Cross-run pagination resume and detail caching are not implemented in this change.

## Verification

- 259 local unittest methods passed, including 16 new pagination/production tests.
- Stage 7, 8, 9 and 10 protected freeze checks passed without changing their manifests.
- V1.0 release evidence remains historical. V1.1 has a separate integrity manifest;
  it does not reuse the old live acceptance as evidence of full V1.1 production success.
- No production state mutation or Telegram delivery was performed in these local tests.

The actual modified collectors were called with `max_jobs=None` against live sources.
Workday used discovery only; SmartRecruiters and PageUp used `enrich_detail=False`.
Thus these measurements verify listing discovery, not full description completeness.

| Source | Old production cap | New observed unique records | Evidence |
|---|---:|---:|---|
| Griffith | 20 | 49 | API total 49 reached |
| Western Sydney | 20 | 36 | API total 36 reached |
| Flinders | 20 | 38 | API total 38 reached over 2 pages |
| Sydney | 20 | 93 | API total 94; repeated-page stop, PARTIAL |
| Monash | 20 | 80 | Repeated-page stop after 5 responses, PARTIAL |
| Queensland | 20 | Not established | Live attempt timed out; no success claimed |

Sydney's advertised-total/unique-ID mismatch is not presented as a proven missing
suitable vacancy. Likewise, these all-role counts are not profile-specific recall.
Full production execution and end-to-end report verification remain pending.

## Regression cases

Tests exercise more than 20 Workday records, Workday's subsequent zero totals,
SmartRecruiters beyond 100 records, PageUp's More Jobs link, repeated pages,
short pages with further results, explicit diagnostic limits, early-empty versus
advertised-total mismatch, page-two errors retaining page-one rows, failed countries
not preventing later countries, cross-query duplicate first pages, LinkedIn native
pagination, University Vacancies pagination, same-origin links, production kwargs,
and propagation of incomplete coverage to source/shard health.
