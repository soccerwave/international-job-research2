# L2 — LLM Evaluator v0.1 Shadow Mode

Status: IMPLEMENTED ON SHADOW BRANCH

## Scope

L2 implements the first independent semantic LLM evaluator without changing the deterministic production evaluator.

Pipeline:

`canonical job -> L0 input builder -> candidate profile V1.1.0 -> independent model transport -> structured JSON validation -> shadow JSONL + telemetry`

## Authority boundary

The LLM remains shadow-only.

- It does not mutate production recommendation, score, tier or durable job state.
- It does not receive the deterministic evaluator decision, score, tier, reasons, keyword hits or evaluation dimensions before producing its own result.
- Rule/LLM comparison remains a later stage.

## Context policy

Full job description is the primary semantic evidence. The complete versioned candidate profile is supplied separately in the model prompt. Structured metadata is supporting evidence only.

L2 intentionally does not implement section extraction, boilerplate cleanup or smart truncation. Those belong to L3. Explicit source-derived `responsibilities_text`, `essential_criteria_text` and `desirable_criteria_text` are passed through only if those fields already exist.

## Missing text behavior

Evidence quality is normalized from source availability after model output:

- `FULL` + non-empty full JD -> `FULL_JD`, confidence cap 100
- `PARTIAL` + non-empty text -> `PARTIAL_JD`, confidence cap 80
- other available source text -> `LIMITED`, confidence cap 55
- no usable source text -> `INSUFFICIENT`, confidence cap 30

These caps prevent a model from claiming high confidence when the source evidence is degraded. They do not change fit scores or decisions.

## Model boundary and cost readiness

The evaluator depends on an `LLMTransport` protocol rather than a specific vendor or model. A transport returns model name, token usage and latency when available. This allows later model tiering, batching, caching and escalation of important disagreements without changing L2 semantics.

No model is selected or authorized as production authority in L2.

## Storage

Shadow results are written separately as JSONL records using `LLM_SHADOW_RESULT_V0.1`. Telemetry is a separate JSONL stream.

Current telemetry events:

- `llm_evaluation_start`
- `llm_api_failure`
- `llm_response_invalid`
- `llm_evaluation_stored`

Malformed JSON, schema-invalid output and API/transport failures are visible and do not mutate production state.

## Acceptance criteria

L2 is acceptable when tests prove that:

1. rule-based conclusions cannot leak into the LLM input or prompt;
2. full JD and candidate profile are actually presented to the model transport;
3. structured output is validated against the frozen L0 schema;
4. degraded vacancy evidence lowers allowed confidence;
5. malformed JSON and transport failures create telemetry;
6. valid results are stored only in a separate shadow stream;
7. no production evaluator or production recommendation path is modified.

## Deferred to later roadmap stages

- L3: context cleanup, section preservation and truncation policy
- L4: 700–1000/day sampling strategy
- L5: independent rule/LLM comparison and disagreement categories
- L6+: human review, benchmark, calibration and eventual safe promotion
