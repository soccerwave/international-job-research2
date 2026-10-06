# L1 Acceptance: Candidate Profile Representation

Status: ACCEPTED — CV-GROUNDED V1.1

L1 is complete when the candidate profile used by the LLM is versioned, grounded in CV evidence, semantically expressive, separated from search preferences, bounded against overclaiming, and independently testable.

## Required artifacts

- `schemas/llm_candidate_profile.schema.json`
- `config/llm_candidate_profile_v1.json`
- `tests/test_llm_candidate_profile_l1.py`
- `LLM_EVALUATOR_FREEZE_L1.1.json`

## CV grounding

Version `LLM_CANDIDATE_PROFILE_V1.1.0` was audited against the current five-page CV supplied for the project before L2 implementation.

The evidence profile now explicitly captures supported facts including:

- PhD in Exercise Physiology - Neuromuscular, MSc in Exercise Physiology, and BSc in Biology
- MSCA postdoctoral fellowship and prior postdoctoral/research-associate experience
- exercise intervention and randomized controlled trial experience
- physiological, fitness, psychological and cognitive assessment experience
- cortisol/stress-biology research and NR3C1 methylation exposure
- MRI-related brain-health research without claiming specialist independent fMRI preprocessing
- animal exercise-neuroscience methods and behavioral testing
- teaching, supervision and mentoring experience
- prior professional experience as an Exercise Physiologist, fitness instructor and coach
- English: Fluent and Spanish: Intermediate (B1)

## Evidence versus preference boundary

The profile has two distinct semantic layers:

1. `evidence_profile`: claims supported by CV evidence.
2. `search_preferences`: targeting choices about role families and preferred or adjacent domains.

A search preference must never be treated as evidence that the candidate possesses a qualification. Valid CV evidence must also not be discarded merely because it lies outside a preferred search domain.

## Acceptance criteria

1. The candidate profile is separate from the deterministic evaluator and contains no vacancy-specific rule-based decision.
2. CV-supported evidence and search preferences are structurally separate.
3. Methods use explicit proficiency levels: `CORE`, `STRONG`, `WORKING`, `EXPOSURE`, or `DO_NOT_CLAIM`.
4. Exposure-level experience cannot silently be promoted to specialist expertise.
5. Neuroimaging experience is represented without claiming advanced independent fMRI preprocessing expertise.
6. Transferable skills are explicit so interdisciplinary vacancies can be judged semantically rather than by exact keyword overlap.
7. English Fluent and Spanish B1 are explicit evidence; higher or other local-language proficiency must not be inferred.
8. Hard constraints and `do_not_infer` guardrails prevent unsupported assumptions about registration, degrees, work authorization and unsupported specialist methods.
9. Recall > Precision is explicit; plausible interdisciplinary roles should prefer `REVIEW` over an unjustified `SKIP` when evidence is incomplete.
10. Job title alone is not decisive; full responsibilities and requirements remain primary evidence under the L0 contract.
11. The profile is versioned independently so later CV or preference changes require an explicit version update.

## Explicit non-goals

L1 does not:

- call an LLM API
- select a model or vendor
- alter the deterministic evaluator
- change production recommendations
- implement sampling
- define the final prompt template
- define model thresholds
- infer missing legal, credential or work-authorization facts

## Exit condition

With profile V1.1 frozen, proceed to L2: LLM Evaluator v0.1 implementation in shadow mode.
