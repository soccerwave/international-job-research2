# L7.3 — Durable Shadow Experiment Evidence Store

Status: IMPLEMENTED ON BRANCH

Purpose: preserve the evidence needed to judge Rule versus LLM performance after the two-week shadow experiment without relying on Excel or Telegram as the source of truth.

## Storage model

Each experiment run is stored as one immutable R2 object:

`llm/experiments/YYYY-MM-DD/<run-id>/evidence.json`

Objects are created with `If-None-Match: *`.

If the same run ID is written again, the write fails explicitly rather than overwriting historical evidence.

The L6.1 semantic evaluation cache remains separate:

`llm/cache/evaluations-v0.1.jsonl`

Cache answers the question "has this exact semantic request already been evaluated?"

Experiment evidence answers the question "what happened in this particular shadow run?"

## Evidence captured

Each run bundle stores:

- run ID and date;
- model;
- candidate profile version;
- MAIN Full evaluations;
- Rescue cheap-triage evaluations;
- Rescue Full evaluations;
- Rule recommendation and evaluator version;
- LLM decision, fit score, confidence and evidence quality;
- hard blocker fields;
- short LLM reason;
- evaluation/triage IDs;
- cache fingerprints and cache-hit status;
- input/output token usage;
- latency;
- disagreement rows;
- failures;
- aggregate counts for API calls, cache hits and tokens.

The Full JD itself is not duplicated into the experiment bundle. A SHA-256 hash of the Full JD is stored so a run can be tied to the exact vacancy text version without duplicating large text payloads.

## Why this is separate from Excel

The Excel workbook is the human review interface.

The immutable R2 bundle is the experiment source of truth used later for metrics, cost analysis and audit.

Telegram remains notification/visibility only.

## Durability

Evidence bundles are immutable per run and are stored separately from:

- authoritative production state;
- LLM cache;
- user-facing Excel artifacts.

This prevents a later run from silently changing the historical record of an earlier run.

## CLI

`scripts/persist_llm_experiment_evidence.py`

Inputs:

- canonical records;
- L7.1 Full-evaluation records;
- L7 Rescue-triage records;
- disagreement rows;
- failure rows;
- run ID/date/model/profile version.

It always writes a local evidence JSON file and can additionally persist it to R2 with:

`--persist-r2`

## Scope boundary

L7.3 does **not** yet:

- call GPT-6 Luna on live jobs;
- wire the shadow experiment into the production workflow;
- start the two-week experiment clock;
- add random Full-JD audit sampling of CLEARLY_OUT_OF_SCOPE triage rejects;
- make LLM decisions authoritative;
- calculate final L8-L11 quality conclusions.

The next operational action after L7.3 is a very small paid smoke test to verify API authentication, model access, token accounting, cache reuse and R2 evidence persistence before live shadow execution begins.
