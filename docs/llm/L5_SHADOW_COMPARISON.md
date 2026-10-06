# L5 — Independent Shadow Comparison

Status: IMPLEMENTED ON L5 BRANCH

## Purpose

Compare the already-produced independent LLM shadow result with the deterministic evaluator result after LLM evaluation has finished.

The comparison stage is post-hoc only:

`independent LLM result + existing deterministic evaluation -> comparison record`

Nothing produced by L5 is fed back into the LLM prompt.

## Comparison inputs

L5 joins by stable job ID and requires:

- a canonical job containing the existing deterministic evaluation;
- a completed `LLM_SHADOW_RESULT_V0.1` record for the same job.

A canonical job without a shadow result is normal because L4 samples only part of the corpus. L5 compares only the shadow results that actually exist.

Duplicate shadow results for one job or a shadow/canonical job-ID mismatch are rejected rather than silently adjudicated.

## Explicit disagreement classes

L5 records the roadmap disagreement cases explicitly, including:

- `RULE_SKIP_LLM_STRONG_APPLY`
- `RULE_SKIP_LLM_APPLY`
- `RULE_REVIEW_LLM_STRONG_APPLY`
- `RULE_REVIEW_LLM_APPLY`
- `RULE_APPLY_LLM_SKIP`

Because E0.1 also has `LOW_PRIORITY`, L5 additionally preserves:

- `RULE_LOW_PRIORITY_LLM_STRONG_APPLY`
- `RULE_LOW_PRIORITY_LLM_APPLY`

These are comparison labels only. They do not promote, demote or hide production jobs.

## Decision distance

For audit visibility, L5 represents recommendation ordering as:

- rule: `SKIP=0`, `LOW_PRIORITY=1`, `REVIEW=2`, `APPLY=3`, `STRONG_APPLY=4`
- LLM: `SKIP=0`, `REVIEW=2`, `APPLY=3`, `STRONG_APPLY=4`

`decision_distance = LLM rank - rule rank`

Positive distance is an LLM uprank; negative distance is an LLM downrank. Absolute distance of two or more receives `DECISION_DISTANCE_GE_2`.

This is an ordinal disagreement indicator, not a fabricated deterministic score.

## Rule score limitation

The current deterministic evaluator/reporting contract explicitly has no single composite score. Therefore L5 does **not** invent one merely to satisfy a nominal "score disagreement" field.

Comparison records contain:

- `llm_fit_score`: the real LLM 0–100 fit score;
- `rule_score: null`;
- `score_comparison_status: UNAVAILABLE_NO_RULE_COMPOSITE_SCORE`.

If a real deterministic composite score is added to a future authoritative contract, score comparison can be versioned then.

## Output schema

Schema: `schemas/llm_shadow_comparison.schema.json`

Version: `LLM_SHADOW_COMPARISON_V0.1`

Each row includes:

- job/evaluation IDs;
- rule evaluator version and recommendation;
- LLM decision, fit score, confidence and evidence quality;
- ordinal decision distance and direction;
- disagreement tags;
- explicit rule-score unavailability status.

## Authority boundary

L5 does not:

- alter the production deterministic evaluator;
- expose rule conclusions to the LLM before its decision;
- change L4 sampling;
- create human adjudication labels;
- promote `SKIP` jobs automatically;
- remove positive rule-based jobs;
- invent a deterministic numeric score.

Human adjudication belongs to L6.

## Acceptance criteria

L5 is acceptable when tests prove that:

1. `Rule SKIP / LLM STRONG_APPLY` is explicitly visible;
2. `Rule SKIP / LLM APPLY` is explicitly visible;
3. `Rule REVIEW / LLM APPLY` and STRONG_APPLY are visible;
4. `Rule APPLY/STRONG_APPLY / LLM SKIP` is visible;
5. LOW_PRIORITY upranks are retained rather than discarded;
6. decision direction and distance are deterministic;
7. rule score is never invented;
8. comparison does not mutate either input;
9. mismatched and duplicate shadow records are rejected;
10. absence of a shadow result for an unsampled canonical job is normal.

Next roadmap stage after L5 is L6 human review queue.
