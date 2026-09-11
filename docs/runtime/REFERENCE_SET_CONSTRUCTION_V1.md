# Stage 7.2 Independent Reference Set Construction

Status: ACTIVE_COLLECTION. Stage 7.2 is not complete until the prospective window closes and the reference set is frozen with eligibility adjudicated.

## Window

- Start: 2026-09-11
- End: 2026-09-24
- Capture grace end: 2026-09-26
- Cadence: daily
- Timezone: Europe/Madrid

## Independence boundary

Reference observations must be acquired from public source surfaces without using pipeline output and without invoking or importing pipeline collector code. The source roster is frozen before any comparison with pipeline output.

Reference eligibility must be adjudicated before any pipeline match status is added. The pre-match schema intentionally contains no pipeline-match fields.

## Frozen source roster

The roster contains 16 public reference surfaces: two per core market.

| Market | Reference surface 1 | Reference surface 2 |
| --- | --- | --- |
| NL | AcademicTransfer | University of Amsterdam vacancies |
| DE | academics.de | University of Cologne job portal |
| IE | University Vacancies | Trinity College Dublin vacancies |
| GB | jobs.ac.uk | University of Oxford jobs |
| BE | Ghent University jobs | KU Leuven Jobsite |
| FR | CNRS Emploi | Inserm recruitment |
| AU | Monash University careers | Uni Roles Australia |
| AT | University of Vienna jobs | TU Wien career portal |

The roster deliberately mixes surfaces already directly represented in production with external or unwired surfaces. This allows Stage 7 to measure both collector/discovery misses and source-coverage misses without changing production first.

Raw reference observations and daily capture logs are not tracked in the public Git repository. They are acquired by a dedicated independent Playwright/Chromium workflow that does not import or invoke production collectors, then encrypted with AES-256-CBC/PBKDF2 before persistence to the private R2 backend. Git may retain only schemas, the frozen roster, the non-sensitive manifest, aggregate counts, dataset digests, and certification evidence. Raw page snapshots are not retained; only cryptographic page fingerprints may be retained as provenance.

`Uni Roles Australia` is included as a known unwired reference surface because Stage 6 registered `uniroles_au` as a structural wiring gap. Including it in the reference roster does not authorize adding it to production.

## Files

- `config/reference/stage7_reference_roster_v1.json`: frozen source roster
- `schemas/reference_vacancy.schema.json`: pre-match reference vacancy contract
- `data/reference/stage7/reference_set_manifest_v1.json`: active collection manifest
- `schemas/reference_capture.schema.json`: daily source-capture contract
- private encrypted R2 object `stage7/reference/v1/reference_observations_v1.jsonl.enc`: append-only reference observations
- private encrypted R2 object `stage7/reference/v1/reference_capture_log_v1.jsonl.enc`: append-only source-day capture evidence
- `src/runtime/reference_set.py`: read-only construction status
- `scripts/verify_stage7_2_reference_set.py`: setup verifier
- `scripts/capture_stage7_reference.py`: independent browser acquisition and encrypted R2 persistence
- `.github/workflows/stage7-reference-capture.yml`: daily 08:00 Europe/Madrid capture schedule during the frozen window
- `tests/test_stage7_2_reference_capture.py`: independent capture helper tests

## Completion rule

Stage 7.2 expects 224 source-day capture slots (16 frozen surfaces × 14 days). Each source-day must end as `CAPTURED_COMPLETE` or a documented resolved exception. Stage 7.2 can be marked DONE only after the full 14-day window has ended, all reference observations have provenance, all eligibility statuses have been adjudicated or explicitly retained as pending according to policy, and the reference set itself is frozen before Stage 7.3 matching begins.

## Daily execution semantics

The live reference capture is separate from production. It uses the frozen 16-surface roster, a headless Chromium browser, broad vacancy-like anchor capture, and at most five generic pagination hops per surface. Because generic pagination cannot prove exhaustive board coverage, a technically successful browser capture is recorded as `CAPTURED_PARTIAL` unless a stronger completeness claim is separately certified. Blocked, unavailable, empty-parser, and retry-required states are preserved explicitly rather than silently treated as complete.

Each source-day has one canonical capture ID. The encrypted R2 observation object is deduplicated by stable reference vacancy ID, while the encrypted capture log retains source-day provenance. The workflow is scheduled for 08:00 Europe/Madrid during September 2026 by running at 06:00 UTC and the capture script itself refuses to collect outside the frozen 11 to 24 September window.

## Live validation

The dedicated GitHub Actions capture path was live-validated on 2026-09-11 in workflow run 34591889595. The first attempt persisted 16 source-day capture events and 293 unique reference observations to the encrypted private R2 objects. Statuses were 14 CAPTURED_PARTIAL and 2 ACCESS_BLOCKED. A same-day rerun completed with zero pending sources and zero new capture events while preserving 16 total capture events and 293 unique observations, validating source-day idempotency. No raw page snapshots were persisted and neither pipeline output nor production collector code was used.
