# L7 — Cheap Rescue LLM Triage

Status: IMPLEMENTED ON BRANCH

Purpose: cheaply decide which Rescue-only candidates deserve a full-JD LLM review without turning the triage into a second rule-based evaluator.

## Inputs

The triage receives only low-cost vacancy metadata:

- title;
- institution;
- department when available;
- location/country;
- role family and role level when available;
- employment/contract type;
- source URL.

It does **not** receive:

- full JD;
- responsibilities text;
- essential/desirable criteria text;
- rule-based recommendation, score, reason or dimensions.

The candidate context is also compressed to the information needed for routing:

- career stage summary;
- degree fields;
- target role families;
- core domains;
- adjacent domains.

## Binary decision

The output has exactly two operational decisions:

- `PASS_TO_FULL_REVIEW`
- `CLEARLY_OUT_OF_SCOPE`

There is deliberately no `UNCERTAIN` state.

Ambiguous, generic, incomplete, interdisciplinary, adjacent or plausibly transferable vacancies must pass to full review. `CLEARLY_OUT_OF_SCOPE` is reserved for obvious occupational/scientific mismatches.

The triage is not allowed to make the final fit/eligibility/methods/application-strength decision.

## Anti-overfiltering policy

The system prompt explicitly requires:

- uncertainty => `PASS_TO_FULL_REVIEW`;
- absence of exact exercise keywords is not grounds for rejection;
- generic research/postdoc titles should not be discarded merely because metadata is incomplete;
- health, psychology, neuroscience, physiology, rehabilitation, ageing, behavior, lifestyle, digital health and human-performance roles are examples of areas that normally deserve a full read when plausible.

This stage optimizes only the cost of deciding whether the Full JD is worth reading. It does not optimize final precision.

## Cache

Successful triage results use the same versioned cache-fingerprint infrastructure as full evaluations.

A triage result is reused only when the effective request is unchanged, including:

- vacancy routing metadata;
- candidate summary;
- triage prompt/schema;
- model/transport identity.

Therefore the first triage is paid, while an unchanged repeat is a cache hit.

## Auditability

Each result stores:

- job ID;
- triage ID;
- decision;
- short reason;
- model;
- input/output tokens;
- latency;
- cache fingerprint and hit status.

The short reason exists for later human audit; it does not add a third decision threshold.

## Scope boundary

L7 does **not** yet:

- invoke Full-JD evaluation for passed Rescue jobs;
- change MAIN evaluation;
- replace REVIEW_MORE in the Excel;
- create LLM_RESCUED output;
- add random audit sampling of rejected Rescue jobs;
- grant LLM production authority;
- wire paid API execution into the production workflow.

Those are later roadmap stages.
