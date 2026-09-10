# Stage 6.3 Structural Completeness Checks

Status: implementation candidate pending CI and freeze closure.

This step audits the structure already present in the repository. It does not decide whether the board set is complete and does not add or remove sources.

## Deterministic checks

- Every configured target country has at least one explicit production coverage row.
- Every tenant registered in active ATS modules is wired into production.
- Every configured LinkedIn Europe partition is wired into production.
- Standalone collectors in `src/sources/core/portals.py` are compared with production source IDs.
- Shared reporting keys are surfaced.
- Sources without explicit configured geography remain visible for later evidence review.

## Current structural findings

Review findings:

- `uniroles_au` has an existing concrete collector (`collect_uniroles`) but is not wired into production.
- `jobs_ac_uk`, `academics_de`, `ecss`, `dvs`, and `fens` have no explicit configured country list and therefore remain unresolved for later evidence review.

Informational findings:

- `cnrs_emploi` also has an alternate implementation in `portals.py`, while production uses the dedicated CNRS module.
- `university_vacancies_ie` also has an alternate implementation in `portals.py`, while production uses the dedicated University Vacancies module.
- `linkedin_australia` and `linkedin_europe` intentionally share the reporting key `linkedin_mads`.

These findings are structural observations only. None is promoted to a confirmed gap in Stage 6.3.

## Current pass conditions

- 13 target countries are represented by explicit production wiring.
- 17 registered ATS tenants are all wired.
- 4 LinkedIn Europe partitions are all wired.
- 6 standalone `portals.py` collectors are accounted for.

Run:

`python scripts/verify_stage6_3_structural_completeness.py`

The verifier is read-only.
