# Live LLM Shadow Wiring

Status: IMPLEMENTED ON BRANCH

This stage connects the existing GPT-6 Luna shadow evaluator to each successful production cycle without changing Rule authority.

## Execution order

The existing production workflow completes first.

The existing control-plane publisher then:

1. resolves the successful production run;
2. decrypts its canonical records;
3. builds and publishes the normal Rule-based user report exactly as before;
4. only after that publication, runs the GPT-6 Luna shadow experiment.

This ordering is deliberate. OpenAI latency or failure cannot prevent the Rule report from being built and published.

## Shadow inputs

The live shadow runner mirrors the existing control-plane boundaries:

- MAIN = the calibrated actionable JOBS set;
- Rescue candidate pool = the existing REVIEW_MORE candidate pool;
- MAIN has precedence over Rescue.

The Full evaluator still receives only its curated vacancy fields plus candidate profile. Rule output is attached only post-hoc for comparison and evidence.

## LLM flow

For every successful production run:

- Rescue-only candidates receive cheap binary triage;
- PASS_TO_FULL_REVIEW candidates receive Full evaluation;
- all MAIN jobs receive Full evaluation;
- the durable R2 semantic cache suppresses unchanged paid calls;
- the three-sheet LLM shadow workbook is built;
- immutable experiment evidence is persisted in R2.

The Rule evaluator remains authoritative.

## Failure isolation

The Luna step runs after the Rule report is published and is configured continue-on-error.

Therefore an OpenAI outage, API error, or shadow-specific failure does not retroactively fail or alter the Rule production result.

Expected per-job LLM failures are retained in the experiment evidence and shadow summary.

## Artifacts

The human-review LLM workbook and diagnostic files are packaged as an encrypted GitHub Actions artifact retained for 21 days.

The durable experiment source of truth remains the immutable R2 evidence bundle.

## Model

The live experiment is explicitly pinned to:

`gpt-6-luna`

This stage does not perform a model bakeoff and does not grant the LLM production decision authority.
