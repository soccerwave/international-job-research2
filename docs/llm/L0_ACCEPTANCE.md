# L0 Acceptance: LLM Evaluator Contract and Design Freeze

Status: ACCEPTANCE CANDIDATE

L0 is complete only when all criteria below are true.

## Required artifacts

- `docs/llm/LLM_EVALUATOR_CONTRACT_V0.1.md`
- `schemas/llm_evaluator_input.schema.json`
- `schemas/llm_evaluation.schema.json`
- `LLM_EVALUATOR_FREEZE_L0.1.json`

## Acceptance criteria

1. Full vacancy text is explicitly the primary semantic evidence when available.
2. Structured metadata is supporting evidence and cannot replace the full vacancy text.
3. The input schema contains no rule-based decision, score, tier, recommendation, reason or evaluator-derived keyword-hit field.
4. The candidate profile is separately versioned and its exact content is deferred to L1.
5. The output schema is structured and validates the agreed decision labels and 0-100 fit dimensions.
6. `hard_blocker=true` requires a non-empty blocker reason.
7. Evidence quality is explicit so degraded JD coverage is visible rather than silently treated as complete evidence.
8. The LLM remains shadow-only and cannot mutate production recommendations in L0.
9. Rule-based output may be joined only after the independent LLM result exists.
10. L0 is model/vendor agnostic; model selection and API integration are deferred.

## Explicit non-goals

L0 does not:

- call any LLM API
- choose a model
- add production cost
- change the deterministic evaluator
- alter JOBS or REVIEW_MORE output
- add sampling logic
- define the candidate profile content
- define prompt calibration thresholds
- grant authority to the LLM

## Exit condition

When the required artifacts are committed and frozen, proceed to L1: Candidate Profile Representation.
