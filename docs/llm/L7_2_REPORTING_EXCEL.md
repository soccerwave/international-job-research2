# L7.2 — LLM Shadow Reporting / Excel

Status: IMPLEMENTED ON BRANCH

Purpose: create the agreed user-facing shadow report that separates rule-found MAIN jobs from LLM-rescued jobs and makes rule-vs-LLM disagreements auditable.

## New report sheets

The L7.2 report has exactly three sheets:

1. **MAIN**
   - every job supplied as MAIN remains visible;
   - shows `Rule Evaluation` and `LLM Evaluation` side by side;
   - shows an `Agreement` classification;
   - retains MAIN rows even when the LLM evaluation is missing or failed by showing `NOT_EVALUATED`.

2. **LLM_RESCUED**
   - contains only Rescue-origin jobs that passed L7 triage, received a Full-JD evaluation, and were judged by the Full LLM as:
     - `STRONG_APPLY`
     - `APPLY`
     - `REVIEW`
   - Rescue-origin Full evaluations ending in `SKIP` are not shown to the user;
   - provenance remains separate from MAIN. LLM does not silently rewrite MAIN membership.

3. **DISAGREEMENTS**
   - contains MAIN jobs where rule and LLM decisions differ;
   - Rescue rows are not duplicated here because they already appear in `LLM_RESCUED`;
   - disagreements are labelled `MINOR_DISAGREEMENT` or `MAJOR_DISAGREEMENT`.

## MAIN safety

A failed or missing LLM result must never remove a MAIN job.

The report therefore uses:

- `LLM Evaluation = NOT_EVALUATED`
- `Agreement = NO_LLM_RESULT`

when a MAIN Full evaluation is unavailable.

This preserves the existing recall-first guarantee.

## Columns

MAIN includes:

- Change
- Rule Evaluation
- LLM Evaluation
- Agreement
- LLM Confidence
- LLM Reason
- Title
- Country
- Role
- Institution
- City
- Deadline
- Link

LLM_RESCUED includes the two evaluator decisions plus the LLM confidence/reason and vacancy metadata.

DISAGREEMENTS contains disagreement severity plus both decisions and the same review context.

## REVIEW_MORE transition

The **new LLM shadow report does not contain REVIEW_MORE**.

The old deterministic Rescue system remains available in the backend as the candidate pool feeding L6.2/L7. It is not deleted.

The current production publisher is deliberately not switched to the new workbook in L7.2 because paid LLM execution is not wired yet. Until the later runtime/wiring stage, the existing production report remains untouched. This avoids publishing an empty or incomplete LLM report before LLM data exists.

## Independence

L7.2 is post-hoc reporting only.

It does not:

- alter rule decisions;
- alter LLM decisions;
- promote Rescue rows into MAIN;
- send reporting labels back into either evaluator;
- grant production authority to the LLM.

## CLI

A standalone builder is available:

`scripts/build_llm_shadow_excel.py`

Inputs:

- canonical records JSON;
- JSON list of MAIN canonical job IDs;
- L7.1 FullEvaluationRecord JSONL.

Output:

- one workbook with `MAIN`, `LLM_RESCUED`, and `DISAGREEMENTS`.

## Scope boundary

L7.2 does **not** yet:

- wire the new workbook into the production publisher;
- purchase or configure OpenAI API credit/key;
- run GPT-6 Luna on live jobs;
- add the random audit sample of `CLEARLY_OUT_OF_SCOPE` Rescue triage rejects;
- start the two-week shadow experiment.

Those are later roadmap stages.
