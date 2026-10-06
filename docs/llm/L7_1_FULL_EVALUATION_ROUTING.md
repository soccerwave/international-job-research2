# L7.1 — Full Evaluation Routing

Status: IMPLEMENTED ON BRANCH

Purpose: connect the agreed MAIN and Rescue paths to the existing independent Full-JD LLM evaluator without changing reporting or production authority.

## Selection contract

Full-JD evaluation receives:

1. **all MAIN_FULL_REVIEW jobs**
   - MAIN does not depend on Rescue triage;
   - SEEN/NEW/CHANGED status is irrelevant at routing time;
   - the existing evaluation cache decides whether the job requires a paid API call.

2. **only Rescue jobs whose L7 triage result is PASS_TO_FULL_REVIEW**
   - CLEARLY_OUT_OF_SCOPE Rescue jobs do not proceed;
   - Rescue jobs with no triage result are not silently promoted and are reported as missing triage.

## Independence

The canonical job is passed unchanged to the existing ShadowEvaluator.

The Full evaluator does not receive:

- MAIN versus Rescue origin;
- PASS_TO_FULL_REVIEW;
- triage reason;
- rule-based recommendation, score, reason or dimensions.

Only after the independent Full-JD evaluation returns does the routing layer attach provenance:

- MAIN
- LLM_RESCUE

For Rescue evaluations it also retains the triage ID for later audit.

## Cache behavior

L7.1 reuses the existing Full-JD ShadowEvaluator and therefore inherits its durable semantic cache.

This means:

- the first uncached Full evaluation can call the model;
- an unchanged Full evaluation becomes a cache hit;
- changed vacancy content, candidate profile, prompt/schema or model identity triggers a fresh evaluation.

Routing status itself is not added to the Full-evaluation fingerprint or prompt.

## Failure handling

A failed Full evaluation is recorded as a failure for that job and does not prevent other selected jobs from being evaluated.

## Metrics exposed by this stage

The routing layer can summarize:

- selected MAIN count;
- selected Rescue count;
- Rescue rejected by triage;
- Rescue missing triage;
- completed Full evaluations by origin;
- failures;
- cache hits;
- real API evaluations.

## Scope boundary

L7.1 does **not** yet:

- change the user-facing Excel;
- replace REVIEW_MORE with LLM_RESCUED;
- add random audit sampling of CLEARLY_OUT_OF_SCOPE Rescue jobs;
- wire OpenAI billing/API secrets into production execution;
- grant LLM production authority;
- change the Full evaluator prompt/schema.

Those belong to later stages.
