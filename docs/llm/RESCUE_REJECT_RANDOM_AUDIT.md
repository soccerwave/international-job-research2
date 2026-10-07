# Rescue Reject Random Audit

Purpose: measure false negatives introduced by the cheap Rescue triage during the live shadow experiment.

## Population

The audit population contains only Rescue candidates whose cheap triage decision is:

`CLEARLY_OUT_OF_SCOPE`

Candidates that receive `PASS_TO_FULL_REVIEW` are not part of this audit because they already proceed to normal Full review.

## Sample

Each production shadow run samples up to 10 rejected candidates.

Selection is pseudo-random but reproducible. Candidates are ranked by a SHA-256 hash of:

`run_id + job_id`

This gives a different sample across different production runs while guaranteeing that a rerun of the same production run selects the same jobs.

If fewer than 10 rejected candidates exist, all rejected candidates are audited.

## Independent Full review

The sampled jobs are sent to the same independent Full evaluator used elsewhere.

The Full evaluator does not receive:

- the cheap triage decision;
- the audit origin;
- Rule recommendation or score.

`RESCUE_REJECT_AUDIT` provenance is attached only after Full evaluation returns.

## Isolation

Audit results do not enter:

- MAIN;
- LLM_RESCUED;
- DISAGREEMENTS;
- Rule production authority.

They exist only to estimate triage false negatives.

## Evidence

Each run writes:

`rescue_reject_audit.jsonl`

and includes the same audit records inside the immutable R2 experiment evidence bundle under:

`rescue_reject_audit`

The shadow summary records:

- reject population size;
- selected sample size;
- completed and failed audits;
- number whose Full decision is STRONG_APPLY, APPLY or REVIEW;
- cache hits and paid API evaluations.

A favorable Full decision among these sampled rejects is evidence that the cheap triage produced a false negative candidate that deserves later human adjudication.
