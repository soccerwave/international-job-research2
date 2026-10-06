# L6.2 — Dual-Path LLM Routing Contract

Status: IMPLEMENTED ON BRANCH

Purpose: formalize the agreed MAIN and Rescue routing boundary before any Rescue triage model is added.

## Contract

The LLM system has two distinct input paths:

1. **MAIN_FULL_REVIEW**
   - contains every job selected by the existing MAIN report/evaluator;
   - includes jobs marked SEEN as well as NEW, MATERIALLY_CHANGED or REOPENED;
   - on the first LLM run, the entire supplied MAIN set is eligible because the LLM cache is cold;
   - on later runs, the durable evaluation cache suppresses unchanged API work.

2. **RESCUE_TRIAGE**
   - contains jobs supplied by the existing Rescue candidate pool that are not already in MAIN;
   - MAIN always wins on overlap, so one job cannot enter both routes;
   - L6.2 does not decide whether a Rescue candidate is relevant.

## Deliberate non-goals

L6.2 does **not**:

- add the cheap Rescue LLM triage;
- define PASS_TO_FULL_REVIEW or CLEARLY_OUT_OF_SCOPE decisions;
- read or evaluate Full JD content;
- add model/API calls or cost;
- change the rule-based evaluator;
- change production authority;
- change the user-facing Excel sheets;
- remove the current REVIEW_MORE implementation yet.

Those changes belong to later stages.

## Why SEEN is not filtered here

Routing and cache semantics are separate concerns.

A job can be old for the rule-based system but still be unseen by the LLM during the first LLM bootstrap. Therefore L6.2 routes the whole supplied MAIN set. The evaluation cache, not seen/change status, determines whether an API call is necessary.

## Rescue provenance

The existing Rescue system remains a candidate generator in the backend. Its raw high-volume output is not promoted into MAIN by L6.2. The later Rescue triage/full-evaluation stages will determine which Rescue candidates become LLM_RESCUED in reporting.

## Independence

L6.2 only routes canonical job objects. It does not place rule decisions inside the independent LLM prompt. LLM evaluation remains independent and rule-vs-LLM comparison remains post-hoc.
