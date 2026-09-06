# Phase 1 — Stage 2 Coverage Reconciliation

Status: **RECONCILED**

Date: **2026-09-06**

This stage reconciles the Stage 1 source strategy against the production source map and the later source registries. It does **not** certify collector correctness or completeness and it does **not** add new collectors.

## Inputs

- `docs/coverage/STAGE1_FEASIBILITY_AUDIT.md`
- `src/runtime/production_sources.py`
- `config/shared_sources.json`
- `config/core_sources.json`
- `docs/coverage/PHASE1_STAGE1_COLLECTOR_BASELINE.md`
- reference uncapped production run `34029865296`

Machine-readable reconciliation: `validation/collector_coverage_reconciliation_2026-09-06.json`.

## Status contract

Every concrete Stage 1 source/backstop commitment must have exactly one of these statuses:

- `IMPLEMENTED_CERTIFIED`
- `IMPLEMENTED_NOT_CERTIFIED`
- `REDUNDANT_VALIDATED`
- `DEFERRED_WITH_REASON`
- `MISSING_ACTION_REQUIRED`

A historical smoke-test `PASS`, runtime `OK`, or presence in a registry is not Phase 1 certification. `REDUNDANT_VALIDATED` requires measured overlap/recall evidence. Merely writing `deferred` is not enough for `DEFERRED_WITH_REASON` unless an actual reason is recorded.

## Reconciliation result

| Status | Count |
|---|---:|
| IMPLEMENTED_CERTIFIED | 0 |
| IMPLEMENTED_NOT_CERTIFIED | 19 |
| REDUNDANT_VALIDATED | 0 |
| DEFERRED_WITH_REASON | 4 |
| MISSING_ACTION_REQUIRED | 5 |
| **Total reconciled commitments** | **28** |

The important conclusion is that the architecture has many implemented sources, but **none is yet Phase 1 certified**, and no omitted source has yet been proven redundant by measured recall evidence.

## Implemented but not certified

The following Stage 1 commitments are present in production or in an enabled production tenant, but still require the later technical/completeness/recall gates:

- EURAXESS Europe
- LinkedIn Europe
- LinkedIn Australia
- AcademicPositions
- jobs.ac.uk
- ECSS
- dvs Stellenbörse
- FENS Job Market
- AcademicTransfer
- academics.de
- UniversityVacancies Ireland
- CoreHR Ireland
- Belgium SuccessFactors tenants
- CNRS Emploi
- Australia PageUp
- Australia SmartRecruiters
- Australia Workday
- University of Innsbruck
- University of Vienna postdoc SuccessFactors tenant

`IMPLEMENTED_NOT_CERTIFIED` is deliberately conservative. Stage 5/6 accepted representative transport probes, while the Phase 1 baseline exposed uncapped-production failures in several sources and did not establish complete-board or market recall.

## Deferred with a recorded reason

### Netherlands direct institutional backstops

Stage 1 explicitly says direct Netherlands boards remain backstops unless measured AcademicTransfer recall shows a gap. This is an intentional defer policy, not validated redundancy. Stage 7 must perform the recall test.

### United Kingdom direct university backstops

Stage 1 explicitly makes jobs.ac.uk the backbone and defers direct university collectors until a measured recall gap exists. Again, this is a defer policy, not proof that direct boards are unnecessary.

### France ABG

Stage 1 records ABG as valuable but technically more difficult. The later core registry records it as pending measured need after CNRS/shared coverage. It remains deferred until recall evidence justifies implementation.

### Australia UniRoles

The collector exists but is disabled because GitHub-hosted runners receive Cloudflare HTTP 403 on listing, legacy-listing, and sitemap routes, while additional routes are blocked by robots policy. PageUp, SmartRecruiters and Workday provide independent Australian coverage. This is a genuine technical defer reason, not redundancy validation.

## Missing action required

These Stage 1 selected high-value backstops are named again in the later `deferred_backstops` registry, but the repository contains no measured recall/overlap evidence and no concrete defer justification sufficient for this gate:

1. German Sport University Cologne
2. Ruhr University Bochum
3. Charité
4. KU Leuven
5. University of Antwerp

They are therefore **not** classified as forgotten, redundant, or validly deferred. They are `MISSING_ACTION_REQUIRED`.

Before final collector certification each must be resolved by evidence into one of:

- implemented and later certified;
- `REDUNDANT_VALIDATED` after measured recall/overlap evidence; or
- `DEFERRED_WITH_REASON` with a concrete, reviewable justification.

## Corrected earlier assumption: University of Vienna

University of Vienna is not absent from production. `successfactors-belgium-austria` includes an enabled `univie_postdoc` tenant. However, the core registry itself warns that the University of Vienna central portal does not necessarily contain every postdoc. Therefore Vienna is `IMPLEMENTED_NOT_CERTIFIED`, with a Vienna-specific recall check required later.

## Opportunistic markets

Italy, Portugal, Czechia, Poland and Luxembourg remain intentionally shared-source-only in the initial version. No dedicated institutional crawler should be added merely because one does not yet exist. First, the shared sources themselves must pass the technical and recall gates.

Sweden, Canada and Switzerland remain explicit Stage 1 exclusions and are not counted as missing coverage.

## Conditional architecture notes, not missing sources

Stage 1 also mentions Australia SuccessFactors “where applicable”, Teamtailor/Personio reuse, and Ubeeo/Oracle Recruiting Cloud conditional support. No concrete target tenant/source commitment is present for these items in the current Stage 6 registry, so they are tracked as architecture capabilities rather than falsely counted as missing collectors.

## Governance decision

This reconciliation closes the Stage 1 → production accounting gap, but it does not close the collection-quality gap.

From this point forward:

1. no concrete Stage 1 commitment may disappear without a reconciliation status;
2. runtime `OK` is not certification;
3. `REDUNDANT_VALIDATED` requires measured evidence;
4. a bare `deferred` label without a reason is insufficient;
5. the five `MISSING_ACTION_REQUIRED` items block final collector certification until resolved;
6. no new source is promoted in Stage 2.

## Next stage

**Phase 1 Stage 3: technical audit of every existing collector.**

That audit will inspect pagination, termination, deduplication, country filtering, date windows, detail extraction, HTTP failures/retries, 429 handling, repeated pages, production limits, and observability before any source-expansion decision is made.
