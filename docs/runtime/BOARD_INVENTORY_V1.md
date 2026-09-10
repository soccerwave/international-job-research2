# Stage 6.1 Current Board Inventory

Status: implementation candidate pending CI and freeze closure.

This inventory describes only the sources and geographies explicitly wired into the current production configuration. It is not a claim that each board is complete in practice. Actual coverage, overlap, blind spots, and missing boards are deferred to later Stage 6 steps.

## Current production inventory

| Metric | Count |
| --- | ---: |
| Production shards | 17 |
| Source executions across shards | 33 |
| Unique source IDs | 30 |
| Unique report keys | 29 |
| Board families | 17 |
| Institution-specific source executions | 18 |
| Distinct configured institutions | 18 |
| Explicitly configured country codes | 13 |

Configured country codes:

`AT, AU, BE, CZ, DE, FR, GB, IE, IT, LU, NL, PL, PT`

Board families currently represented:

`Academic Positions`, `AcademicTransfer`, `CNRS Emploi`, `CoreHR`, `Deutsche Vereinigung für Sportwissenschaft`, `EURAXESS`, `European College of Sport Science`, `Federation of European Neuroscience Societies`, `LinkedIn`, `PageUp`, `SAP SuccessFactors`, `SmartRecruiters`, `University Vacancies Ireland`, `University of Innsbruck direct portal`, `Workday`, `academics.de`, `jobs.ac.uk`.

Institution-specific wiring currently includes:

`Deakin University`, `Dublin City University`, `Flinders University`, `Ghent University`, `Griffith University`, `Monash University`, `The University of Queensland`, `The University of Sydney`, `Trinity College Dublin`, `UCLouvain`, `UNSW Sydney`, `University College Cork`, `University College Dublin`, `University of Galway`, `University of Innsbruck`, `University of Vienna`, `Vrije Universiteit Brussel`, and `Western Sydney University`.

## Semantics

The machine-readable inventory is built by `src/runtime/board_inventory.py` directly from the current production source map and the tenant configuration already used by collectors. Building the inventory does not execute collectors or make network requests.

Each production execution records:

- production shard
- source ID
- report key
- board family
- board kind
- configured country codes
- configured search locations where applicable
- geography mode
- fixed institution where the source is institution-specific

Sources such as `jobs.ac.uk`, `academics.de`, ECSS, DVS, and FENS are deliberately not assigned invented country coverage when production does not explicitly constrain them to a fixed country list. Later Stage 6 work will evaluate their actual market coverage separately.

Run:

`python scripts/verify_stage6_1_board_inventory.py`

The verifier checks the inventory against the current production source map and the production workflow shard matrix. It is read-only.
