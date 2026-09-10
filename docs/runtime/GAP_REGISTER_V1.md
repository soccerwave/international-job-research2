# Stage 6.4 Evidence-based Gap Register

Status: implementation candidate pending CI and freeze closure.

This step resolves the structural findings from Stage 6.3 into an evidence-backed register. It does not add or remove any production source.

## Classification rules

- `CONFIRMED_STRUCTURAL_GAP`: the repository contains a concrete collector for a target market, but production does not wire that source.
- `NOT_STRUCTURAL_GAP_RECALL_PENDING`: the structural finding does not demonstrate missing wiring, but actual market recall still requires Stage 7 evidence.
- `NOT_GAP`: the finding is informational or already explained by current architecture.

## Current register

Confirmed structural gap:

- `uniroles_au`: `collect_uniroles` exists in `src/sources/core/portals.py`, uses source key `uniroles_au`, and fixes country coverage to Australia, but the source is not present in production wiring.

Recall pending, not structural gaps:

- `jobs_ac_uk`: board-native unfiltered geography; country is preserved from listing evidence rather than forced by production config.
- `academics_de`: country is inferred per listing.
- `ecss`: listing-native thematic geography; complete single-page collection semantics already validated.
- `dvs`: listing-native thematic geography; complete single-page collection semantics already validated.
- `fens`: listing-native thematic geography; no explicit country list is required by current configuration.

Not gaps:

- `cnrs_emploi`: production already uses the dedicated CNRS implementation.
- `university_vacancies_ie`: production already uses the dedicated University Vacancies implementation.
- `linkedin_mads`: the shared report key is intentional across LinkedIn Australia and LinkedIn Europe.

## Decision boundary

`uniroles_au` is registered only. Stage 6.4 does not wire it into production. Whether it should be added is deferred until after Stage 7 Recall Measurement and Stage 8 Gap Analysis.

Run:

`python scripts/verify_stage6_4_gap_register.py`

The verifier is read-only.
