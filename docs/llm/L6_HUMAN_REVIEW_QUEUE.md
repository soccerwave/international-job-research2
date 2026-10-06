# L6 — Human Review Queue

Status: IMPLEMENTED ON L6 BRANCH

## Purpose

Create a human adjudication queue from L5 rule/LLM comparisons without changing production authority.

The queue is downstream of both independent evaluations:

`rule result + independent LLM result -> L5 comparison -> L6 human review queue`

Nothing from L6 is fed back into the LLM prompt or production recommendation.

## Human labels

The allowed adjudication labels are exactly:

- `RULE_CORRECT`
- `LLM_CORRECT`
- `BOTH_REASONABLE`
- `BOTH_WRONG`
- `INSUFFICIENT_INFORMATION`

New queue items start unlabeled. Human notes are optional.

## Recall-first priority

The queue prioritizes likely rule-based false negatives first:

1. Rule `SKIP` / LLM `STRONG_APPLY`
2. Rule `SKIP` / LLM `APPLY`
3. Rule `LOW_PRIORITY` / LLM `APPLY` or `STRONG_APPLY`
4. Rule `REVIEW` / LLM `APPLY` or `STRONG_APPLY`
5. Rule positive / LLM `SKIP`
6. Other disagreements

Agreements are not added to the default L6 queue because L6 is an adjudication queue, not the benchmark itself. L7 can deliberately sample agreements when constructing the gold benchmark.

## Authority boundary

L6 does not:

- change the deterministic production evaluator;
- auto-promote a rule `SKIP`;
- auto-delete a positive rule result;
- alter L4 sampling;
- alter L5 comparisons;
- expose rule conclusions to the LLM before its decision.

## Acceptance criteria

L6 is acceptable when:

1. false-negative candidates are prioritized;
2. rule-positive/LLM-negative disagreements remain reviewable;
3. agreements are excluded from the default disagreement queue;
4. the five roadmap labels are enforced;
5. applying a human label does not mutate the original queue item;
6. no production authority is introduced.

Next roadmap stage after L6 is L7 Gold Benchmark.
