# L4 — Recall-First LLM Sampling Strategy

Status: IMPLEMENTED ON L4 BRANCH

## Purpose

Select a cost-bounded daily shadow-evaluation cohort without reducing collector coverage, mutating production recommendations, or leaking deterministic evaluator conclusions into the LLM prompt.

Sampling changes only **which jobs receive an LLM call**. Once selected, each job still receives the same Full-JD-first L2/L3 context.

## Default target

The default sampling configuration is:

- all `STRONG_APPLY` and `APPLY` jobs;
- up to 250 review-layer jobs;
- up to 150 negative jobs.

This normally places the daily cohort in the intended several-hundred-job range and leaves room for positive volume. It is not a hard 1000-job ceiling. If positive volume alone is large, all positives remain selected.

No collector max-job limit is introduced.

## REVIEW_MORE versus E0.1 REVIEW

`REVIEW_MORE` is a supplemental reporting/control-plane concept, not an E0.1 recommendation value.

Therefore L4 does not pretend they are the same category.

If an external set of `REVIEW_MORE` canonical job IDs is supplied, those jobs have first priority within the 250-job review target. Any unused review quota is filled from E0.1 `REVIEW` jobs.

Without an external `REVIEW_MORE` ID set, the quota is filled from E0.1 `REVIEW` only.

## Negative sampling

The default 150-job negative cohort is split 50/50:

1. `NEGATIVE_TARGETED`: `LOW_PRIORITY`/`SKIP` jobs with FULL/PARTIAL detail and rule metadata indicating ambiguity, adjacency, reviewability or transferable potential, while excluding explicit blocker-coded records from this targeted bucket.
2. `NEGATIVE_BLIND_EXPLORATION`: FULL/PARTIAL `LOW_PRIORITY`/`SKIP` jobs selected without using scientific-fit dimensions or review codes.

The blind half is intentional. Sampling only negatives already considered plausible by the deterministic evaluator would reproduce the evaluator's blind spots and weaken false-negative discovery.

`UNKNOWN` level or methods status alone is not enough to make a negative job targeted, because that would collapse most negatives into the targeted pool.

If either negative sub-pool cannot fill its allocation, the remaining quota is backfilled from other eligible FULL/PARTIAL negative jobs.

## Stratification and reproducibility

Quota-limited pools are selected by deterministic round-robin stratification across:

- country;
- source key.

Within each stratum, a stable SHA-256 rank is derived from:

`seed + sampling bucket + stable job ID`

Using the same seed produces the same sample. A daily seed allows controlled rotation across days.

## Independence boundary

Rule-based metadata is allowed to determine sampling membership because L4 runs before LLM invocation.

It is **not** copied into the L0 LLM input or L2/L3 prompt. The LLM still sees only vacancy evidence plus the candidate profile, preserving the frozen anti-anchoring contract.

Sampling metadata such as bucket and selection rank remains outside the semantic prompt.

## Detail quality

Negative exploration currently requires `FULL` or `PARTIAL` detail because the main purpose is semantic false-negative discovery and low-information negatives are poor use of a limited LLM budget.

Positive jobs remain selected regardless of detail status. L2 evidence-quality/confidence safeguards still apply downstream.

## Authority boundary

L4 does not:

- change the production rule evaluator;
- change JOBS or REVIEW_MORE reporting;
- create a collector cap;
- send rule scores, reasons, dimensions or keyword hits to the LLM;
- implement L5 rule/LLM comparison;
- promote or demote any job.

## Acceptance criteria

L4 is acceptable when tests prove that:

1. all `STRONG_APPLY`/`APPLY` jobs survive sampling even above nominal targets;
2. supplied REVIEW_MORE IDs have priority and E0.1 REVIEW fills unused quota;
3. REVIEW_MORE is not treated as an E0.1 recommendation;
4. negative sampling includes both targeted and blind exploration;
5. unused negative quota is backfilled when possible;
6. FULL/PARTIAL detail is required for negative exploration;
7. sampling is deterministic for the same seed and rotates with a different seed;
8. review and negative quotas are stratified across country/source;
9. duplicate canonical jobs are not selected twice.

Next roadmap stage after L4 is L5 shadow comparison.
