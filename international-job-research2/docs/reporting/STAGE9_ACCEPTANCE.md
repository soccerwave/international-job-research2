# Stage 9 Acceptance — V0.9_REPORTING

Date: 2026-09-04

Status: **ACCEPTED**

Reporting contract: `REPORTING_V1.0.0`

## Scope accepted

Stage 9 turns canonical, evaluated, Stage-8-state-annotated vacancy records into human-review reporting surfaces without introducing a composite evaluator score and without mutating durable state.

The accepted workbook has seven fixed sheets:

1. `SUMMARY`
2. `TODAY_ACTIONABLE`
3. `CURRENT_ACTIONABLE`
4. `REVIEW_QUEUE`
5. `LOW_PRIORITY`
6. `AUDIT`
7. `SOURCES`

Country remains a reporting dimension and is not used to partition the workbook into country-specific sheets.

`CURRENT_ACTIONABLE` contains open `STRONG_APPLY`, `APPLY`, and `REVIEW` records. `TODAY_ACTIONABLE` is limited to actionable `NEW`, `MATERIALLY_CHANGED`, and `REOPENED` events. Ambiguous roles, policy reviews, and unresolved Full JD cases remain visible for human review under the fail-open policy.

## Deterministic acceptance

The final deterministic report used during live acceptance was generated in workflow run `33913219057` against commit `e329832c2c06ac97f0184e0c755f20aa32166daa`.

Artifact:

- artifact id: `9952148653`
- artifact name: `stage9-report-smoke-33913219057-1`
- SHA-256 digest: `5262c50a1800e3f75e96fd3a4ffee4c2ef2e8bc6f162a2601ff45eb151967024`

The deterministic smoke built a real XLSX workbook, JSON summary, Telegram preview, and acceptance JSON. Independent inspection confirmed all seven required sheets and the expected queue counts.

## Regression gate

The final Stage 9 gate passed:

- 12 Stage 9 reporting tests
- deterministic XLSX/Telegram smoke
- 29 Stage 8 state/R2 tests
- 24 Stage 7 regression tests
- 21 Stage 6 regression tests
- 11 Stage 5 regression tests
- 4 Stage 4 regression tests
- Stage 7 freeze verification
- Stage 8 freeze verification
- Stage 9 freeze verification

Total unittest methods in the Stage 4–9 gate: **101 PASS**.

## Live Telegram acceptance

The workflow was manually dispatched with `run_telegram_live=true`.

Live acceptance evidence from run `33913219057`:

- Telegram configuration validation: PASS
- Bot API reachable: PASS
- configured chat count: 2
- deterministic acceptance report build: PASS
- Telegram message delivery: PASS
- XLSX document delivery: PASS
- `telegram-live-acceptance` job: SUCCESS

The existing Telegram bot already used by the Spain project was intentionally reused by adding its credentials as repository secrets for this repository. No new bot was required.

## Failure semantics

Telegram is downstream of durable-state processing. Telegram delivery failure may be retried and must be surfaced operationally, but it must never roll back or invalidate a successful R2 state write.

Reporting consumes Stage 8 state annotations and does not recompute `NEW`, `SEEN`, `MATERIALLY_CHANGED`, or `REOPENED`.

## Freeze

Freeze manifest: `REPORTING_FREEZE_V1.0.0.json`

Freeze status: **ACCEPTED**

Protected reporting files: 11.

Accepted architecture: `HUMAN_REVIEW_FIRST_NO_COMPOSITE_SCORE_FAIL_OPEN_POST_STATE_REPORTING`.

## Acceptance boundaries

Stage 9 does not introduce production scheduling or the integrated production runner. These remain Stage 10 responsibilities, together with shadow runs, failure injection, end-to-end consistency checks, coverage-gap measurement, and release-candidate certification.
