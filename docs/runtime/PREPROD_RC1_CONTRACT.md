# Stage 10 Pre-production RC1 Contract

Status: `CANDIDATE`

Pipeline target: `V0.10_PREPROD_RC1`

Runtime contract: `PREPROD_RC1_CONTRACT_V1.0.0`

## Purpose

Stage 10 is the first integrated execution of the already accepted collection, evaluation, state and reporting layers. It does not change the frozen Stage 7 evaluator, Stage 8 state semantics or Stage 9 reporting behavior.

The central path is:

```text
independent immutable live shards
  -> Stage 4 verified fan-in
  -> conservative cross-source canonicalization
  -> explicit-evidence-only availability
  -> evaluator E0.1
  -> Stage 10 state-identity projection
  -> CENTRAL_FINALIZER state writer
  -> isolated R2 durable state during acceptance
  -> Stage 9 XLSX / optional Telegram reporting
```

## Collection topology

The candidate Stage 10 live shadow uses fourteen independent shard groups:

1. `euraxess-europe`
2. `academicpositions`
3. `linkedin-europe`
4. `linkedin-australia`
5. `uk-ireland-portals`
6. `thematic`
7. `netherlands`
8. `germany-france-primary`
9. `corehr-ireland`
10. `successfactors-belgium-austria`
11. `australia-pageup`
12. `australia-smartrecruiters`
13. `australia-workday`
14. `austria-direct`

A source or tenant failure is isolated inside its shard. A zero-observation result is not treated as closure. A missing shard artifact is surfaced explicitly and cannot silently disappear from the acceptance status.

UniRoles Australia remains deferred under the accepted Stage 6 decision. Other deferred institutional backstops are not silently enabled during Stage 10.

## Canonicalization

Canonicalization is central-only and occurs before evaluation and durable state.

The implementation adapts the conservative identity pattern from the Spain production repository, with stricter international fail-open behavior:

- same-source distinct stable IDs never merge
- contradictory country evidence prevents merge
- explicit shared vacancy URL identity can merge
- distinct reference IDs prevent fuzzy merge
- unresolved cross-source postings are not fuzzily collapsed merely because title and institution look similar
- resolved fuzzy matching requires strong title/institution agreement plus validated Full-JD containment

The preference is to leave a duplicate visible for human review rather than hide a parallel vacancy through an unsafe merge.

Canonical records receive a stable `canonical_id`, retain one conservative anchor source identity, aggregate `observed_by_sources`, and preserve source-level observations under `raw_extra.canonicalization`.

## Evaluation boundary

Stage 5/6 collectors emit `COLLECTOR_ONLY_NOT_PRE_EVALUATED` as a boundary sentinel. Stage 10 removes this sentinel exactly at the central evaluation boundary because it is not substantive review evidence.

All other blocker and review evidence remains preserved. Missing or unresolved Full JD remains reviewable. Source-status conflicts remain reviewable.

Evaluator `E0.1` itself is unchanged and remains protected by `EVALUATOR_FREEZE_E0.1.json`.

## Availability

Stage 10 central availability uses only explicit evidence already present in the canonical record:

- explicit past application deadline may mark `CLOSED`
- explicit future deadline may mark an otherwise `UNKNOWN` record `OPEN`
- explicit rolling/open-until-filled status may mark an otherwise `UNKNOWN` record `OPEN`
- existing explicit `CLOSED` and `ERROR` source status is preserved

Absence from a run, missing shard, source failure or zero observations never implies closure.

## State boundary

Only `CENTRAL_FINALIZER` may write durable state.

Stage 10 acceptance must not touch the production `state/current/state.json`. Live acceptance is restricted by the Stage 10 CLI to R2 prefixes beginning with:

```text
acceptance/stage10/<unique-run-id>/
```

The accepted Stage 8 compare-and-swap implementation and state semantics are reused unchanged.

### State identity projection

Stage 10 adds a state-only identity projection before invoking the frozen Stage 8 writer. This exists because a portal-level `listing_url` or shared apply URL can legitimately be identical across many distinct vacancies. Such a URL is useful provenance but is not a safe durable identity alias when it appears on more than one canonical record in the same observation set.

The projection therefore:

- deep-copies the canonical records
- normalizes URL aliases using the same URL normalizer used by Stage 8
- suppresses `detail_url`, `apply_url`, or `listing_url` only when that normalized URL occurs on more than one distinct canonical record in the batch
- preserves `canonical_id` and `source_key + source_job_id` as strong aliases
- validates that no remaining Stage 8 alias is shared by different canonical IDs before any state publish
- requires one unique `state_id` per canonical record after the write
- copies state annotations back to the original canonical records

The canonical/reporting records retain their original URLs. The projection changes state identity inputs only; it does not change the Stage 8 state engine or its freeze.

A fresh isolated acceptance prefix must map every canonical record to a separate state entry: all observations must be `NEW`, with zero `SEEN`, `MATERIALLY_CHANGED` or `REOPENED`, and `state_jobs` must equal the canonical record count. Replaying the exact same canonical set must then produce only `SEEN`, with zero `NEW`, `MATERIALLY_CHANGED`, `REOPENED`, and zero inferred closure from absence.

## First live shadow finding

The first Stage 10 live shadow run, GitHub Actions run `33917037095` on 2026-09-04, was intentionally not accepted because the replay gate exposed a durable-identity collision.

Collection itself was healthy:

- 14 of 14 expected shard artifacts were present and accepted
- 0 shards were rejected
- 0 sources were marked `ERROR` or `PARTIAL`
- 106 records entered fan-in
- 106 canonical records were emitted and evaluated
- isolated R2 persistence and the XLSX report were created
- `not_observed_inferred_closed` remained 0

However, the initial state generation mapped those 106 canonical records onto only 41 state entries, producing 41 `NEW` and 65 `MATERIALLY_CHANGED`. The exact-set replay then produced only 14 `SEEN` and 92 `MATERIALLY_CHANGED` instead of 106 `SEEN`.

Post-run evidence showed the 106 canonical IDs and 106 source-local job identities were unique. The collisions came from shared board-level URL aliases, especially repeated `listing_url` values, being treated as durable identity aliases by the frozen Stage 8 engine. The replay gate therefore worked as intended and blocked Stage 10 acceptance.

The affected R2 state was isolated under:

```text
acceptance/stage10/stage10-33917037095-1/
```

No production state key was touched. The Stage 10 state-identity projection described above is the candidate correction and must pass deterministic regression plus a new live shadow before Stage 10 can be accepted.

## Reporting boundary

Reporting is generated only after canonicalization, E0.1 evaluation and state annotation. The Stage 9 reporting module is reused unchanged.

The report therefore consumes the same state-annotated canonical records that were written through the finalizer state boundary.

Telegram remains downstream of durable state. Sending a Stage 10 shadow report is optional and cannot affect state success.

## Run statuses

`PASS` requires:

- Stage 4 fan-in not `ERROR`
- no expected shard artifact missing
- no source/tenant diagnostic in `ERROR` or `PARTIAL`
- canonicalization completes and does not expand record count
- every canonical record receives E0.1 evaluation
- fresh isolated state maps one canonical record to one unique state entry
- state `records_observed` equals canonical record count
- reporting `AUDIT` count equals canonical record count
- `not_observed_inferred_closed == 0`

`PARTIAL_PASS` means healthy observations were safely processed but at least one shard/source was missing or degraded. This is operationally useful but is not sufficient for final strict Stage 10 acceptance.

`ERROR` means there was no accepted shard fan-in, so Stage 10 skips both state write and reporting.

## Deterministic failure injection

The Stage 10 regression gate must verify at minimum:

- cross-source resolved duplicate merge
- same-source distinct-ID separation
- reference-ID separation
- unresolved fuzzy merge disabled
- collector sentinel removal before E0.1
- explicit deadline availability behavior
- full local shard-to-XLSX path
- failed shard isolation
- missing shard detection
- prior unobserved vacancy history preserved
- all-failed run skips state write
- zero-observation source remains visible in diagnostics
- multiple distinct vacancies sharing one board-level listing URL remain separate state identities
- the shared-listing fixture is all `NEW` on first state write and all `SEEN` on replay
- state projection never mutates the canonical reporting URLs

## Live strict acceptance

The final strict live acceptance must additionally require:

- all fourteen expected shard artifacts present
- no degraded source diagnostics
- at least one canonical vacancy observed
- isolated R2 initial write succeeds
- initial R2 state has `NEW == canonical_records`, zero material changes, and `state_jobs == canonical_records`
- state identity projection reports one unique state ID per canonical record
- isolated R2 replay succeeds with all canonical records `SEEN` and zero material changes
- Excel report is generated from the integrated records
- all Stage 4–10 regression tests pass
- Stage 7, Stage 8 and Stage 9 freeze verifiers pass unchanged

## Explicitly outside Stage 10

- no production scheduler
- no writes to the production R2 state key during acceptance
- no automatic application submission
- no change to E0.1 scoring/routing behavior
- no change to Stage 8 state semantics
- no change to Stage 9 report sheet contract
- no V1.0 production certification
