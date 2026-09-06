> Production collection update (V1.1): discovery defaults to `all`, replacing the
> historical 20-record probe cap. Paginated APIs/searches continue until exhausted
> or stalled; explicit positive limits remain available for diagnostics. Coverage
> warnings mark failed or repeated pages as PARTIAL. This does not certify market
> completeness or change evaluator suitability rules. See
> [collection evidence](docs/runtime/COLLECTION_V1.1.md).

# International Academic Job Search

Personal academic vacancy search with daily GitHub Actions collection, persistent Cloudflare R2 state, and Telegram reporting.

## Current operation

- **Daily search:** `.github/workflows/production.yml`, cron `17 6 * * *` (06:17 UTC). Actual start time can differ. Manual dispatch is also available.
- **Collection:** 14 shards feed one central finalizer. The finalizer deduplicates, evaluates, and updates authoritative R2 state using compare-and-swap.
- **State prerequisite:** scheduled operation requires existing authoritative state. Use the recovery workflow only for an actual recovery need.
- **Telegram scheduled delivery:** successful scheduled finalization sends the E0.1 operational summary; its audit Excel is attached when `today_actionable > 0` or `TELEGRAM_SEND_REPORT_ALWAYS` is enabled.
- **Telegram control-center Excel button:** the Worker in `soccerwave/researcher-job-search/cloudflare-worker/src/index.js` reads the R2 latest pointer and delivers the E0.2.1 clean Excel. It is a real user-facing report, not just an evaluation artifact.
- **Manual production completion:** after successful publication, the publisher now sends the E0.2.1 summary and clean Excel to the configured Telegram chats, even with zero actionable changes. This applies to manual production runs, including the control-center Run button. Push-triggered publication and standalone publisher dispatch do not send a report. Delivery failure fails the publisher job after the report has been stored; the Excel button can still retrieve it.
- **Actionable changes:** non-closed vacancies classified STRONG_APPLY, APPLY, or REVIEW with NEW, MATERIALLY_CHANGED, or REOPENED events. This includes review candidates; it is not a guarantee of suitability.
- **Evaluator distinction:** production state and direct Telegram reporting use frozen **E0.1**. The separate control-plane publisher builds the cleaner **E0.2.1** report after successful production runs. These reports have different filters.
- **No LLM work is planned:** Roadmap 3 is stopped under the personal project's no-paid-API constraint. E1.1 is used only for the supplemental REVIEW_MORE sheet; production state evaluation remains E0.1. This is a user-authorized visibility supplement, not a claim of validated classifier superiority.

## Actions to use

| Workflow | Purpose |
| --- | --- |
| International Academic Job Search Production (`production.yml`) | Daily search or manual run |
| `publish-control-plane-report.yml` | Publish the separate clean report after successful production |
| `recover-production-state.yml` | Deliberate state recovery |
| `test-control-plane-report-publisher.yml`, `test-stage4.yml` through `test-stage10.yml`, `test-v1.yml` | Regression and frozen-baseline protection |

Sixteen completed evaluator experiment workflows are [archived](archive/README.md) outside the active Actions directory. Historical Actions runs may remain visible in GitHub.

## Repository map

| Path | Purpose |
| --- | --- |
| `src/sources/` | Vacancy collectors |
| `src/runtime/`, `src/state/` | Collection, finalization and durable state |
| `src/evaluation/` | Production evaluator, clean-report evaluator and retained research implementations |
| `src/reporting/` | Operational Excel, Telegram and clean user report |
| `config/`, `schemas/` | Policies, sources and data contracts |
| `scripts/`, `tests/` | Entrypoints, maintenance and regression checks |
| `docs/` | Contracts and historical stage records |
| `validation/` | Historical evaluator evidence; not daily runtime input |
| `archive/` | Retired workflow definitions and earlier README |

Historical E0.4–E0.8 scripts, implementations, validation fixtures and status files are retained together to preserve reproducibility and their existing path dependencies. Their presence does not indicate an active development roadmap. Root freeze manifests remain authoritative for accepted runtime components.

## Operational evidence

The scheduled run [33961120243](https://github.com/soccerwave/international-academic-job-search/actions/runs/33961120243) on 2026-09-05 completed all 14 shards, reported 39 actionable changes under E0.1, and returned `{"ok": true, "delivered": true}` from Telegram delivery. One successful run is evidence of current operation, not a guarantee of future delivery.

For runtime details see [production contract](docs/runtime/PRODUCTION_CONTRACT.md), [state persistence](docs/runtime/STATE_PERSISTENCE_CONTRACT.md), and [reporting contract](docs/reporting/REPORTING_CONTRACT.md).

## Two-sheet user report

- `JOBS` preserves the E0.2.1 clean list and its eight columns.
- `REVIEW_MORE` adds nonclosed records excluded from JOBS but surfaced by the pinned E1.1 candidate. `RESCUE_REVIEW` means evaluator disagreement; `NEEDS_DETAIL_REVIEW` means insufficient or delegated evidence. These are unconfirmed candidates for manual review.
- Review rows include a reason and state event, with NEW/MATERIALLY_CHANGED/REOPENED first. Unchanged records stay available without being labelled new. Closed records and JOBS records are excluded from the supplement.
- E1.0/E1.1 implementations were copied unchanged from commit b447229f7ab466e3635963467cd4a4de375714a4. No state or accepted evaluator files were changed.
- Both the Telegram Excel button and manual-completion delivery use this workbook. Summary `current_actionable`/`today_actionable` retain JOBS semantics; `review_more_count`, `review_more_types`, `review_more_changes`, and `total_visible` describe the supplement separately.
