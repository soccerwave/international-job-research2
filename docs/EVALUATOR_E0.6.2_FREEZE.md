# Evaluator E0.6.2 candidate freeze

Status: `FROZEN_FOR_FRESH_BLIND_VALIDATION`

Evaluator: `E0.6.2_CONTEXT_LOCALIZATION_CANDIDATE`

Frozen source: `src/evaluation/calibrated_e062.py`

Frozen Git blob: `703327844b12a7e885da1ddf477e4feb22c87db3`

## What is established

The candidate passes the complete burned development suite at workflow run `33967658063`:

- E0.5 failed fresh-blind set: 64/64 exact match
- E0.4.2 burned blind set: 42/42 exact match
- E0.3 burned validation set: 38/38 exact match
- temporal development set: 17/17 exact match
- 24 E0.6-family generalization counterexamples pass
- accepted V1 production freeze remains unchanged

These results are development/regression evidence only. Every listed labeled set has informed evaluator development and therefore cannot certify promotion.

## What is not established

E0.6.2 is **not promoted**, is not wired into the production evaluator, and is not wired into the user-facing clean report. The final holdout remains sealed.

Promotion requires a production inventory collected after this exact candidate freeze is merged to `main`, independent prediction-blind human labels locked on that fresh inventory, and one scoring pass of this exact frozen blob against the declared gate:

- accuracy >= 0.90
- surfaced precision >= 0.90
- surfaced recall >= 0.75
- critical false negatives = 0

Any evaluator behavior change after this freeze starts a new candidate cycle and invalidates the pending fresh-blind gate for E0.6.2.
