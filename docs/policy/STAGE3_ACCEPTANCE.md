# Stage 3 Acceptance — V0.3_DATA_POLICY_CONTRACT

## Required artifacts

- `schemas/vacancy.schema.json`
- `config/markets.json`
- `config/roles.json`
- `config/scientific_profile.json`
- `config/language_policy.json`
- `config/mobility_policy.json`
- `config/blockers.json`
- `config/decision_policy.json`
- `tests/fixtures/sample_vacancy.json`
- `docs/policy/DATA_POLICY_CONTRACT.md`
- `docs/policy/MOBILITY_POLICY_REFERENCES.md`

## Acceptance checks

1. Every JSON artifact parses successfully.
2. Every normalized role family used by role policy is represented by the vacancy schema.
3. Core, opportunistic and excluded markets match the Stage 1 scope.
4. France faculty remains out of scope.
5. Australia no-sponsorship plus explicit existing-work-rights requirement remains a hard blocker.
6. Full-JD failure routes to `NEEDS_DETAIL_REVIEW`, never directly to skip.
7. Sponsorship silence is not a hard blocker.
8. Preferred MRI is not a blocker.
9. Scientific capabilities and `do_not_infer` constraints are both explicit.
10. Mobility remains separate from scientific fit.
11. No production collector, evaluator, state engine, reporting engine or scheduler is introduced in Stage 3.

## Freeze boundary

After Stage 3 acceptance, policy/config edits must update the relevant policy version and `CHANGELOG.md`.

Stage 4 may implement validation and runtime handling of this contract, but must not silently change the policy semantics.
