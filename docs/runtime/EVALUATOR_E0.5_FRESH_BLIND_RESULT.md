# Evaluator E0.5 fresh blind validation result

E0.5 was frozen before collection of the production inventory used for promotion validation. The frozen evaluator blob is `5855915e3b2a0024c765814b024290bd07d19db7`.

## Fresh source inventory

- Production workflow run: `33964408465`
- Production artifact: `9968973897`
- Artifact digest: `sha256:473e9afbf15d45bc9963664741dab037dc8909461f2ed1fd2821d6d6a929039e`
- Source inventory: 500 canonical records
- Run occurred after E0.5 freeze was merged to `main`.

## Prediction-blind labels

A stratified 64-record sample was selected without using E0.5 predictions. All canonical IDs previously human-labelled in E0.3, E0.4 temporal development, or the E0.4.2 blind set were excluded. Human labels were committed as `b496fbe9dbd1ae256e3b74ca89baab8640bb18bf` before any successful E0.5 scoring attempt.

The first scoring infrastructure run `33965124547` failed at Python import (`ModuleNotFoundError: No module named 'src'`) before the candidate was imported or predictions were generated. The entrypoint was corrected without changing the frozen candidate or locked labels.

## First actual blind score

Workflow run `33965199215` produced the first E0.5 predictions for this fresh sample.

- Selection: 64
- Correct: 53
- Accuracy: 0.828125
- Expected surfaced: 11
- Predicted surfaced: 15
- Surfaced precision: 0.5333333333333333
- Surfaced recall: 0.7272727272727273
- Critical false negatives: 3

Promotion thresholds were accuracy >= 0.90, surfaced precision >= 0.90, surfaced recall >= 0.75, and zero critical false negatives. All four gates failed.

Decision: **REJECT_E0.5_FOR_PROMOTION**.

E0.5 remains immutable and `NOT_PROMOTED`. The 64-record sample is now burned and may be used only as development evidence for a new evaluator candidate cycle. The accepted V1 production/runtime freeze remains unchanged.

The three critical false negatives identify the main safety problem for the next cycle: plausible adjacent health/biomedical roles were hard-skipped because inherited specialist or missing-anchor rules were too aggressive. False positives also remain in unrelated faculty/discipline roles, so the next candidate must improve both recall and precision rather than relaxing all gates globally.
