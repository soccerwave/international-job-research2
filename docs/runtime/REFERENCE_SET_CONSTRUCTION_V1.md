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

`Uni Roles Australia` is included as a known unwired reference surface because Stage 6 registered `uniroles_au` as a structural wiring gap. Including it in the reference roster does not authorize adding it to production.

## Files

- `config/reference/stage7_reference_roster_v1.json`: frozen source roster
- `schemas/reference_vacancy.schema.json`: pre-match reference vacancy contract
- `data/reference/stage7/reference_set_manifest_v1.json`: active collection manifest
- `data/reference/stage7/reference_observations_v1.jsonl`: append-only reference observations
- `schemas/reference_capture.schema.json`: daily source-capture contract
- `data/reference/stage7/reference_capture_log_v1.jsonl`: append-only source-day capture evidence
- `src/runtime/reference_set.py`: read-only construction status
- `scripts/verify_stage7_2_reference_set.py`: setup verifier

## Completion rule

Stage 7.2 expects 224 source-day capture slots (16 frozen surfaces × 14 days). Each source-day must end as `CAPTURED_COMPLETE` or a documented resolved exception. Stage 7.2 can be marked DONE only after the full 14-day window has ended, all reference observations have provenance, all eligibility statuses have been adjudicated or explicitly retained as pending according to policy, and the reference set itself is frozen before Stage 7.3 matching begins.
