# L1 Acceptance: Candidate Profile Representation

Status: ACCEPTANCE CANDIDATE

L1 is complete only when the candidate profile used by the LLM is versioned, semantically expressive, bounded against overclaiming, and independently testable.

## Required artifacts

- `schemas/llm_candidate_profile.schema.json`
- `config/llm_candidate_profile_v1.json`
- `tests/test_llm_candidate_profile_l1.py`
- `LLM_EVALUATOR_FREEZE_L1.0.json`

## Acceptance criteria

1. The candidate profile is separate from the deterministic evaluator and does not encode the current rule-based decision for any vacancy.
2. Core scientific domains and adjacent domains are represented separately.
3. Methods include explicit proficiency levels: `CORE`, `STRONG`, `WORKING`, `EXPOSURE`, or `DO_NOT_CLAIM`.
4. Exposure-level experience cannot silently be promoted to specialist expertise.
5. Neuroimaging experience is represented without claiming advanced independent fMRI preprocessing expertise.
6. Transferable skills are explicit so interdisciplinary vacancies can be judged semantically rather than by exact keyword overlap.
7. Hard constraints and `do_not_infer` guardrails prevent unsupported assumptions about professional registration, degrees, work authorization, local-language proficiency, specialist wet-lab methods, and other unsupported credentials.
8. Recall > Precision is explicit in the profile guidance; plausible interdisciplinary roles should prefer `REVIEW` over an unjustified `SKIP` when evidence is incomplete.
9. Job title alone is not decisive; full responsibilities and requirements remain primary evidence under the L0 contract.
10. The profile is versioned independently so future profile changes require an explicit version update.

## Explicit non-goals

L1 does not:

- call an LLM API
- select a model or vendor
- alter the deterministic evaluator
- change production recommendations
- implement sampling
- define the final prompt template
- define model thresholds
- infer missing legal, language or credential facts

## Exit condition

When the profile, schema, tests and freeze manifest are committed, proceed to L2: LLM Evaluator v0.1 implementation in shadow mode.
