# V1 Production Runtime Contract

Contract version: `PRODUCTION_RUNTIME_V1.0.0`

Release target: `V1.0_VALIDATED_OPERATIONAL_INTERNATIONAL_PIPELINE`

Status: V1 state contract accepted; collection policy superseded by V1.1 (see COLLECTION_V1.1.md).

## Purpose

V1 promotes the accepted Stage 10 pre-production path into the authoritative operational runtime without changing the frozen evaluator, state semantics, reporting contract, or Stage 10 canonicalization/identity behavior.

The production layer is deliberately thin. It wraps the frozen Stage 10 collection and finalization components, adds production-only safety gates, points durable state at the authoritative root R2 key, schedules recurring execution only after a successful bootstrap, and provides an explicit CAS-safe recovery path.

## Frozen dependencies

Production depends on and must verify these accepted freezes before any authoritative state mutation:

- `EVALUATOR_FREEZE_E0.1.json`
- `STATE_FREEZE_V1.0.0.json`
- `REPORTING_FREEZE_V1.0.0.json`
- `PREPROD_FREEZE_V1.0.0.json`

V1 does not modify their protected files.

## Collection topology

Production uses the same 14 independent collection shards accepted in Stage 10:

1. `euraxess-europe`
2. `academicpositions`
3. `linkedin-europe`
4. `linkedin-australia`
5. `uk-ireland-portals`
6. `thematic`
7. `netherlands`
8. `germany-france-primary`
9. `corehr-ireland`
10. `successfactors-belgium-austria`
11. `australia-pageup`
12. `australia-smartrecruiters`
13. `australia-workday`
14. `austria-direct`

Production uses `production_sources.py`, independently of the historical Stage 10 low-volume probe map. `PRODUCTION_MAX_JOBS_PER_SOURCE=all` is the default and imposes no record cap. Positive integers are explicit diagnostic overrides, without the former 20-record clamp. Native pagination or next-page links are followed until exhaustion, repetition, or an error. Partial results survive later-page failures; coverage warnings propagate as PARTIAL source health. The GitHub job timeout is 360 minutes, not a target search duration.

LinkedIn continues to use the pinned Mads transport commit `fd89eac178dc546d41f6c1a3213de88d96112c6d`.

## Authoritative state

Production durable state is exactly:

`state/current/state.json`

The production state store must have an empty R2 prefix. Acceptance/test prefixes are rejected by the production runtime.

All state mutations still pass through the accepted `CENTRAL_FINALIZER` writer boundary and Stage 8 compare-and-swap persistence.

## First production bootstrap

The first authoritative state write is intentionally stricter than normal fail-open operation.

Before any bootstrap mutation, the strict production preflight requires:

- every expected production shard artifact is present and valid
- every shard is `OK`
- every source diagnostic is `OK`
- no `PARTIAL`, `ERROR`, or `UNKNOWN` source health
- at least one accepted record
- successful canonicalization and E0.1 evaluation
- canonical schema validity
- zero remaining cross-record durable identity collisions

If any condition fails, the strict release returns `STRICT_PREFLIGHT_FAILED` and records `state_write=SKIPPED_BEFORE_MUTATION`. The authoritative production state remains untouched.

Bootstrap is allowed only through an explicit manual release-acceptance run. The workflow refuses `bootstrap_production=true` unless `release_acceptance=true`.

## Normal operational runs

After authoritative state exists, recurring runs use the accepted fail-open semantics:

- a missing or failed source never implies vacancy closure
- a missing or failed shard never implies vacancy closure
- source `UNKNOWN`/`ERROR` never becomes closed
- healthy observations may still advance state during a partial run
- only explicit source/deadline evidence may change lifecycle state
- state identity conflicts fail the write rather than silently merging histories
- R2 stale writers are rejected by ETag compare-and-swap

A normal production run may therefore complete as `PARTIAL_PASS` while preserving unobserved historical jobs.

## Scheduling

The production workflow is scheduled daily with:

`17 6 * * *`

GitHub Actions cron is UTC, so this corresponds to approximately 08:17 in Barcelona during CEST and 07:17 during CET.

The schedule is deliberately inert before first bootstrap. The readiness job checks `state/current/state.json`; if it does not exist, scheduled execution exits successfully with `run_allowed=false` and no collection shards start.

Once the strict live release successfully creates authoritative state, the same schedule becomes active automatically.

Production uses one shared concurrency group:

`international-academic-production`

`cancel-in-progress` is false. A production run and recovery run therefore cannot intentionally execute concurrently through the supplied workflows.

## Telegram and Excel

The accepted Stage 9 reporting implementation remains unchanged.

For the first strict V1 release:

1. Telegram credentials/chat accessibility are validated before the production state mutation.
2. The production state and report are generated.
3. The Excel report is sent to Telegram without `continue-on-error`.
4. V1 release evidence is written only after Telegram delivery succeeds.

For routine scheduled runs, Telegram is downstream and best-effort. A transient Telegram failure cannot roll back a successful durable-state write.

The workbook retains the seven accepted sheets:

- `SUMMARY`
- `TODAY_ACTIONABLE`
- `CURRENT_ACTIONABLE`
- `REVIEW_QUEUE`
- `LOW_PRIORITY`
- `AUDIT`
- `SOURCES`

## Release acceptance

The strict live V1 release profile is:

`V1_PRODUCTION_LIVE_RELEASE`

The post-write strict gate requires:

- final core status `PASS`
- zero missing shards
- zero degraded sources
- source health `UNKNOWN=0`
- positive canonical record count
- state observed count equals canonical count
- durable state identity cardinality matches canonical count
- inferred closure from absence equals zero
- persistence current key equals `state/current/state.json`

If the authoritative state did not exist before the release, the first production generation must additionally satisfy:

- every canonical record is `NEW`
- state job count equals canonical count
- zero `MATERIALLY_CHANGED`
- zero `REOPENED`

If an earlier strict release wrote production state but failed later, for example during Telegram delivery, a repeat strict release may observe existing records as `SEEN`; it does not require a destructive re-bootstrap.

## Recovery contract

Recovery is manual-only and accepts source objects only under:

- `state/backups/`
- `state/bootstrap/`

The recovery workflow requires the operator to type `RESTORE` exactly.

Recovery never copies an older state object directly over `state/current/state.json`. Instead it:

1. reads and validates the immutable backup
2. verifies SHA-256 metadata when present
3. reads the current authoritative state and ETag
4. copies the selected backup content into a new state document
5. sets generation to `current generation + 1`
6. records a recovery run ID and current timestamp
7. publishes through the existing R2 `If-Match` CAS path
8. reads back and verifies the restored state

This preserves monotonic generation history and prevents a stale/manual restore from silently overwriting a newer writer.

## Failure boundaries

- Collection source failure: fail-open; represented in shard/source diagnostics.
- Missing shard: fail-open after bootstrap; strict release rejects it before first bootstrap.
- Canonical/schema/identity failure: finalizer fails; no successful new authoritative generation is certified.
- CAS conflict: write rejected; operator reruns from current state.
- Telegram failure during routine operation: state remains valid; notification is best-effort.
- Telegram failure during strict release: release is not certified, even if state was already written; rerun strict release against the existing state.
- Recovery failure before CAS: authoritative current state is unchanged.

## Production credentials

The workflow uses the already-established repository configuration:

Secrets:

- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_IDS`

Variables:

- `R2_BUCKET`
- `R2_ENDPOINT`
- optional `TELEGRAM_SEND_REPORT_ALWAYS`
- optional `PRODUCTION_MAX_JOBS_PER_SOURCE`

No credentials are stored in the repository.

## Acceptance boundary

Creation and deterministic CI of this runtime do not by themselves make V1 accepted. V1 becomes operationally accepted only after a strict manual production release succeeds against the authoritative root state, Telegram and report evidence are independently verified, the V1 release freeze is finalized, and the final bookkeeping CI passes on the accepted release HEAD.

## Daily trigger ownership (2026-09-06)

The shared Cloudflare Worker in soccerwave/researcher-job-search owns International's
daily dispatch at 06:00 Europe/Madrid. UTC 04:00 and 05:00 cron events are filtered
using the scheduled event timestamp and the Madrid time zone; exactly one dispatches
on each day, including DST transition days. Spain's 03:17 UTC trigger is unchanged.
Both International Telegram and cron requests send max_jobs_per_source=all.
The duplicate native GitHub schedule is removed; workflow_dispatch remains available.
Deployment is verified before migrating this workflow. A scheduler initiates the
search, so 06:00 is a start time, not a guaranteed report-delivery time.
