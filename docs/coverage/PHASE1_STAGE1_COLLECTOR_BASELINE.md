# Phase 1 — Stage 1 Collector Baseline Freeze

Status: **FROZEN BASELINE**

Date: **2026-09-06**

Purpose: capture the exact pre-repair collection state before collector certification work begins. This is a snapshot, not a claim that the current collectors are correct or complete.

## Baseline identity

- Repository: `soccerwave/international-academic-job-search`
- Baseline branch: `main`
- Baseline commit: `61af22729a7a27060646dca8f0ed365ba0435b95`
- Production collector producer version: `V1.1_PAGINATED_DISCOVERY`
- Reference production run: GitHub Actions run `34029865296`
- Runtime run id: `prod-34029865296-1`
- Workflow conclusion: `cancelled`
- Final production status: `PARTIAL_PASS`
- Production artifact id: `9989035983`
- Production artifact digest: `sha256:d26fd920e252091fd0dfe4afb50abbeb249b1d97e74f325a9a74e802967fa909`
- Production mode: uncapped (`PRODUCTION_MAX_JOBS_PER_SOURCE=all`)

PR #30 (`fix/linkedin-progress-diagnostics`, head `8b50f4ba299281e26681c0b7e80518847254dfbf`) was open and unmerged when this baseline was frozen. Its changes are explicitly **not part of the baseline**.

## Production topology at baseline

The production map contains 14 shards:

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

Source policy comes from `src/runtime/production_sources.py`; production shard ids remain inherited from the Stage 10 shard topology through `src/runtime/live_shards.py`.

## Reference run outcome

The cancelled reference run published 13 of 14 expected shard artifacts. `linkedin-europe` did not publish a shard artifact.

- Raw input records: **4,222**
- Canonical records: **3,960**
- Duplicates removed: **262**
- Merged clusters: **155**
- Cross-source clusters: **154**
- Accepted shards: **13 / 14**
- Missing shards: **`linkedin-europe`**
- State generation after finalization: **14**
- Source health summary: **22 OK / 7 PARTIAL / 1 ERROR**

Important: the counts above are baseline observations only. `OK` here means the current runtime emitted no warning for that source; it does **not** certify complete board coverage or relevant-job recall.

## Source snapshot

| Source | Runtime status | Records | Baseline note |
|---|---:|---:|---|
| academicpositions | PARTIAL | 466 | Multiple country/page requests ended in HTTP 404; 159 full descriptions unavailable |
| academics_de | OK | 609 | Not yet coverage-certified |
| academictransfer | OK | 10 | Not yet coverage-certified |
| cnrs_emploi | OK | 4 | Not yet coverage-certified |
| corehr_dcu | OK | 6 | Not yet coverage-certified |
| corehr_galway | OK | 16 | Not yet coverage-certified |
| corehr_tcd | OK | 10 | Not yet coverage-certified |
| corehr_ucc | OK | 33 | Not yet coverage-certified |
| corehr_ucd | OK | 10 | Not yet coverage-certified |
| dvs | PARTIAL | 26 | 3 full descriptions unavailable |
| ecss | OK | 2 | Not yet coverage-certified |
| euraxess | PARTIAL | 10 | Repeated-page failures for NL/DE/IE/GB/BE; 429 exhaustion for FR/AT/IT/PT/PL/LU; CZ country facet missing |
| fens | OK | 76 | Not yet coverage-certified |
| jobs_ac_uk | PARTIAL | 845 | 2 full descriptions unavailable; coverage still requires independent certification |
| linkedin_mads (Australia) | PARTIAL | 1,407 | Australia lecturer search failed with HTTP 400 after deep pagination |
| pageup_deakin | OK | 19 | Not yet coverage-certified |
| pageup_monash | PARTIAL | 80 | Repeated-page termination |
| pageup_unsw | OK | 108 | Not yet coverage-certified |
| shard::linkedin-europe | ERROR | 0 | Expected shard artifact missing after cancellation |
| smartrecruiters_griffith | OK | 49 | Not yet coverage-certified |
| smartrecruiters_western_sydney | OK | 36 | Not yet coverage-certified |
| successfactors_ghent | OK | 17 | Not yet coverage-certified |
| successfactors_uclouvain_science | OK | 4 | Not yet coverage-certified |
| successfactors_univie_postdoc | OK | 23 | Not yet coverage-certified |
| successfactors_vub | OK | 10 | Not yet coverage-certified |
| uibk | OK | 13 | Not yet coverage-certified |
| university_vacancies_ie | OK | 129 | Not yet coverage-certified |
| workday_flinders | OK | 38 | Not yet coverage-certified |
| workday_uq | OK | 73 | Not yet coverage-certified |
| workday_usyd | PARTIAL | 93 | Repeated-page termination |

## Known baseline defects and uncertainties

These are recorded as known facts/uncertainties before repair work starts:

1. **LinkedIn Europe observability failure.** The shard ran for roughly 47m48s without useful intermediate progress output and was cancelled before publishing its normal shard artifact. The baseline cannot identify the actual internal bottleneck from that run alone.
2. **EURAXESS coverage failure.** The implementation did not function as a reliable European backbone in the reference run.
3. **AcademicPositions incomplete coverage.** Multiple country listings terminated with request failures and a material share of detail pages were unavailable.
4. **LinkedIn Australia partial coverage.** The broad uncapped lecturer search eventually failed with HTTP 400.
5. **Monash PageUp and University of Sydney Workday reported repeated-page termination.** Whether those stops represent harmless terminal behavior or missed listings remains uncertified.
6. **Runtime `OK` is weaker than collector certification.** Existing status logic does not prove completeness against the live source board.
7. **The cancelled run still finalized available shards and advanced authoritative state to generation 14.** This behavior is part of the frozen baseline and will be evaluated later under production safety.
8. **Stage 1 source strategy has not yet been reconciled against production.** Missing/deferred/redundant backstops are intentionally left for Phase 1 Stage 2.

## What is frozen

Until Phase 1 collector work says otherwise:

- Evaluator/scoring logic is out of scope and must not be tuned in response to collector output.
- This baseline commit/run is the comparison point for collection changes.
- Existing source counts must not be interpreted as target counts.
- No missing Stage 1 backstop is automatically promoted into production in this stage.
- A future collector may only be called `CERTIFIED` after board-completeness and recall evidence are added in later stages.

## Evidence pointers

- Stage 1 strategy: `docs/coverage/STAGE1_FEASIBILITY_AUDIT.md`
- Production source map: `src/runtime/production_sources.py`
- Production shard runtime/status logic: `src/runtime/production_shards.py`
- Reference workflow run: `34029865296`
- Reference final production artifact: `9989035983`
- Open diagnostic-only LinkedIn PR excluded from baseline: `#30`

## Stage completion

**Phase 1 Stage 1 is complete when this baseline is committed and reviewable.**

Next stage: **Phase 1 Stage 2 — Stage 1 → Production Coverage Reconciliation.** Every source/backstop from the original strategy must receive an explicit status: `IMPLEMENTED_CERTIFIED`, `IMPLEMENTED_NOT_CERTIFIED`, `REDUNDANT_VALIDATED`, `DEFERRED_WITH_REASON`, or `MISSING_ACTION_REQUIRED`.
