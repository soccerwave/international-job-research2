# Phase 1 Stage 4.9: Full-JD semantics

## Scope

This stage fixes the systemic Full-JD classification defect only. It does not change pagination, query taxonomy, source coverage, evaluator/scoring, retry/backoff, date normalization, or source selection.

## Stage 3 defect

The Stage 3 audit found that `FULL` was commonly inferred from a text-length threshold (`>= 200` characters). The source scan on 2026-09-06 found length-dependent Full-JD hints in AcademicPositions, common generic detail fetching, FENS, LinkedIn/Mads, jobs.ac.uk, EURAXESS, University Vacancies Ireland, CoreHR, Workday, and SmartRecruiters. Length is not evidence that a complete job description was retrieved.

## Canonical semantic contract

`make_record()` is now the authority for canonical `description.detail_status`.

- `FULL`: non-empty detail text was obtained through a registered source-specific detail contract, structured detail API, source-specific job-detail route/parser, or the ECSS vacancy PDF contract.
- `PARTIAL`: useful non-empty text exists, but the retrieval path does not itself establish completeness.
- `UNAVAILABLE`: no usable detail text was returned.
- `FETCH_FAILED`, `BLOCKED`, and `NOT_ATTEMPTED`: preserved as operational states.

Character count is not used by the canonical decision.

## Registered complete-detail contracts

Exact source keys:

- `academicpositions`
- `academictransfer`
- `academics_de`
- `cnrs_emploi`
- `ecss`
- `euraxess`
- `fens`
- `jobs_ac_uk`
- `linkedin_mads`
- `uibk`
- `uniroles_au`
- `university_vacancies_ie`

Registered prefixes:

- `corehr_`
- `pageup_`
- `smartrecruiters_`
- `successfactors_`
- `workday_`

A source is registered only because its collector targets a known job-detail contract. Registration is explicit, rather than inferred from text size.

## Generic HTML and PDF behavior

`fetch_detail_text()` no longer promotes long generic HTML to FULL. Successful generic HTML extraction is `PARTIAL` regardless of length. A successfully parsed full PDF returns a FULL retrieval hint, but the canonical record still requires an appropriate source contract; ECSS is explicitly registered because its advertised vacancy detail is the PDF itself.

`dvs` is deliberately not registered: it uses generic HTML extraction, so useful detail remains `PARTIAL` unless a stronger source-specific completeness contract is implemented later.

## Compatibility

Several collectors still contain their historical local FULL/PARTIAL length hints. These values are no longer authoritative: `make_record()` normalizes them under the evidence contract before any canonical record leaves the collector. Keeping those local hints avoids a broad multi-collector rewrite in this bounded stage while eliminating their effect on output semantics.

## Validation

Focused regressions require status invariance across short and long text when evidence is unchanged. They verify that a short registered-source detail can be FULL, a very long unregistered generic page remains PARTIAL, empty text cannot be FULL, and operational failure states survive normalization.

A bounded live gate exercises real Workday and PageUp detail retrieval and verifies that canonical records from these registered contracts remain FULL with non-empty JD text. Full all-source board certification remains a later stage.
