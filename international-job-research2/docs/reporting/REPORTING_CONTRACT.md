# Reporting Contract — REPORTING_V1.0.0

Stage 9 turns canonical, evaluated, state-annotated vacancy records into human-review reporting surfaces. Reporting is downstream of collection, canonicalization, evaluation, and durable-state classification. It does not recompute or mutate durable state.

## Principles

1. Human review is a first-class architectural stage, not an exception path.
2. There is no single composite score. Stage 7 evaluator dimensions remain visible independently.
3. Ambiguity stays visible. `REVIEW`, `NEEDS_DETAIL_REVIEW`, `POLICY_REVIEW`, and unresolved Full JD records remain in the review queue unless explicitly closed.
4. Missing or failing sources remain visible in source health. Zero observations never imply a vacancy closed.
5. Country is a reporting dimension, not a workbook partition. No sheet-per-country topology is used.
6. Reporting is read-only with respect to Stage 8 state.
7. Telegram delivery is a post-state side effect. A Telegram failure must never roll back, rewrite, or invalidate a successful durable-state write.

## Input contract

The report builder consumes a JSON array of canonical evaluated records. Records may carry:

- Stage 7 evaluation at `evaluation` or `raw_extra.evaluation`
- Stage 8 state annotation at `raw_extra.state`
- optional Stage 8 run summary
- optional per-source diagnostics

The builder does not infer state events itself. It reports the event already assigned by Stage 8.

## Action queues

### CURRENT_ACTIONABLE

Open/non-closed records whose recommendation is one of:

- `STRONG_APPLY`
- `APPLY`
- `REVIEW`

### TODAY_ACTIONABLE

The actionable subset whose Stage 8 state event is one of:

- `NEW`
- `MATERIALLY_CHANGED`
- `REOPENED`

`SEEN` records do not reappear here simply because they were observed again.

### REVIEW_QUEUE

Open/non-closed records are retained when any of the following is true:

- recommendation is `REVIEW`
- pre-evaluation disposition is `NEEDS_DETAIL_REVIEW`
- pre-evaluation disposition is `POLICY_REVIEW`
- Full JD/detail status is unresolved (`FULL` and `PARTIAL` are the only resolved reporting states)

This queue is intentionally fail-open.

### LOW_PRIORITY

Open/non-closed `LOW_PRIORITY` records.

### AUDIT

All observed records, including `SKIP`, for traceability.

## Workbook contract

The workbook has exactly these human-review surfaces:

1. `SUMMARY`
2. `TODAY_ACTIONABLE`
3. `CURRENT_ACTIONABLE`
4. `REVIEW_QUEUE`
5. `LOW_PRIORITY`
6. `AUDIT`
7. `SOURCES`

The summary contains run counts, recommendation distribution, Stage 8 event distribution, state generation/job count, top actionable countries, and source health.

Job rows expose the evaluator dimensions separately: scientific fit, career level, methods, language, mobility, registration context, and contract. The evaluator reason, review/blocker codes, deadline, Full JD status, source, and direct vacancy URL remain visible.

## Telegram contract

Telegram summary messages contain:

- current actionable count
- `STRONG_APPLY`, `APPLY`, and `REVIEW` counts
- `NEW`, `MATERIALLY_CHANGED`, and `REOPENED` counts
- review-queue and low-priority counts
- source health
- whether actionable changes exist in the current run

The XLSX document is attached when actionable changes exist, or when `TELEGRAM_SEND_REPORT_ALWAYS=true` is explicitly configured.

Temporary Telegram/network failures are retryable. Configuration/API rejection is treated as permanent delivery failure. In both cases the failure belongs to the reporting/delivery layer only and must not invalidate the already accepted Stage 8 state generation.

## Runtime entry points

- `scripts/build_stage9_report.py`
- `scripts/send_stage9_telegram.py`
- `scripts/run_stage9_smoke.py`

## Donor provenance

Stage 9 adapts patterns from the Spain production repository pinned in the donor registry:

- `scripts/build_cloud_report.py` → workbook organization, frozen headers, links, filters, summary/source-health presentation
- `scripts/telegram_notify.py` → Telegram environment contract and transient/permanent retry semantics

International changes remove score-centric assumptions, expose the Stage 7 multidimensional evaluator, add Stage 8 event semantics, introduce a fail-open review queue, and prohibit sheet-per-country reporting.
