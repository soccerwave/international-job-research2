# Phase 1 — Stage 3 Collector Technical Audit

Status: **COMPLETE — REPAIR REQUIRED BEFORE CERTIFICATION**

Date: **2026-09-06**

Baseline main SHA: `3152fb74ce1d3d0e9b138744b383146366b4cb59`

Reference uncapped production run: `34029865296`

Scope: technical audit of every collector currently present in the production source map. This stage does **not** modify collector behavior, evaluator logic, scoring, state, reporting, or source expansion.

## Audit dimensions

Each collector was reviewed for:

1. pagination and stop semantics;
2. deduplication and stable identifiers;
3. country/location handling;
4. query/date-window recall risk;
5. Full JD retrieval and status semantics;
6. retry, rate-limit and transient-failure handling;
7. observability and failure propagation;
8. cancellation durability/checkpointing;
9. metadata extraction, especially dates and location;
10. evidence from the uncapped production run.

Audit labels:

- `BLOCKER`: current behavior prevents production certification.
- `MAJOR`: material correctness or recall defect requiring repair.
- `DEGRADED`: source works but an observed defect remains.
- `PROVISIONAL_PASS`: no source-specific blocker was observed, but the source is not certified and still inherits systemic defects.

No source is marked certified in Stage 3.

## Executive result

Production source instances audited: **30**.

- `BLOCKER`: **3**
- `MAJOR`: **5**
- `DEGRADED`: **1**
- `PROVISIONAL_PASS`: **21**

The collection layer is salvageable, but it is **not production-certifiable yet**. The strongest current collectors are the API-backed University Vacancies Ireland and SmartRecruiters tenants, followed by the Workday tenants that completed without pagination warnings. The weakest current collectors are EURAXESS and LinkedIn; AcademicPositions is materially degraded.

## Source-by-source findings

| Source | Run evidence | Audit | Main finding |
|---|---:|---|---|
| EURAXESS Europe | 10 records, PARTIAL | **BLOCKER** | Repeated pages for NL/DE/IE/GB/BE; 429 retry exhaustion for FR/AT/IT/PT/PL/LU; CZ facet missing. Only NL records survived. Current pagination has no advertised total/next signal and rate-limit handling is not source-adaptive. |
| LinkedIn Europe | shard missing after cancellation | **BLOCKER** | 47m48s inside the collector with no useful progress output and no partial shard artifact. Serial location × query pagination followed by serial detail enrichment makes runtime opaque and cancellation destroys all in-flight work. |
| LinkedIn Australia | 1,407 records, PARTIAL | **BLOCKER** | Completed in about 13 minutes but lecturer discovery failed after deep pagination with HTTP 400. Same serial architecture and no durable discovery/detail checkpoint. |
| AcademicPositions | 466 records, PARTIAL | **MAJOR** | 11 country/page 404 failures, including base-page failures for Ireland/Portugal/Poland; 159 detail fetch failures. Terminal 404 versus real failure is not distinguished. Requested country code is authoritative even when detail metadata may disagree. |
| jobs.ac.uk | 845 records, PARTIAL | **MAJOR** | Discovery is high-yield, but location parsing is materially wrong: baseline analysis found 65 obvious foreign postings labelled `GB`, 28 location fields longer than 200 characters, only 2 parsed deadlines, and zero parsed posted dates. Production query set is also incomplete for recall-sensitive role families such as Research Associate. |
| CNRS Emploi | 4 records, OK | **MAJOR** | Parser filters at collection time for `postdoc/postdoctor/chercheur` plus URL patterns. This is a collector-layer recall filter and can silently exclude valid France research roles before the evaluator sees them. |
| PageUp Monash | 80 records, PARTIAL | **MAJOR** | Repeated-page termination. Shared `next_listing_url()` treats generic labels such as `More Jobs` as pagination; that can point back to a listing root rather than a true next page. |
| Workday Sydney | 93 records, PARTIAL | **MAJOR** | Advertised-total pagination ended on a repeated page before clean completion. Must reconcile unique IDs against the API total and determine whether the final item is inaccessible, duplicated, or offset handling differs for this tenant. |
| dvs | 26 records, PARTIAL | **DEGRADED** | 3 Full JDs unavailable; two records had unresolved country. Single-page collector emits no explicit board-completeness coverage event. |
| University Vacancies Ireland | 129 records, OK | **PROVISIONAL_PASS** | Strongest current contract: public API, advertised total, source status, posted date and deadline in payload. Still inherits the global `FULL >= 200 chars` semantics. |
| SmartRecruiters Western Sydney | 36 records, OK | **PROVISIONAL_PASS** | API pagination uses `totalFound`; strong discovery contract. Posted timestamps are not normalized by current generic date parser. |
| SmartRecruiters Griffith | 49 records, OK | **PROVISIONAL_PASS** | Same strengths and metadata caveat as Western Sydney. |
| Workday UQ | 73 records, OK | **PROVISIONAL_PASS** | Advertised-total CXS pagination completed. POST listing calls are not covered by the generic GET-only retry policy. |
| Workday Flinders | 38 records, OK | **PROVISIONAL_PASS** | Same as UQ; no observed pagination defect in baseline. |
| PageUp Deakin | 19 records, OK | **PROVISIONAL_PASS** | No observed failure, but it shares the same generic HTML-next-link risk that failed on Monash. |
| PageUp UNSW | 108 records, OK | **PROVISIONAL_PASS** | No observed failure, but same shared pagination-link risk. |
| AcademicTransfer | 10 records, OK | **PROVISIONAL_PASS** | HTML next-link collector completed without warning, but no board total exists and metadata extraction is sparse; completeness remains unproven. |
| academics.de | 609 records, OK | **PROVISIONAL_PASS** | High-yield and no pagination warning. Country inference is heuristic and defaults to Germany; posted/deadline metadata was absent from all 609 baseline records. |
| CoreHR UCD | 10 records, OK | **PROVISIONAL_PASS** | No observed pagination failure; dynamic search can require POST, while the shared retry adapter retries GET only. |
| CoreHR DCU | 6 records, OK | **PROVISIONAL_PASS** | Same CoreHR contract; no source-specific failure observed. |
| CoreHR UCC | 33 records, OK | **PROVISIONAL_PASS** | Same CoreHR contract; raw deadlines were present but normalization failed. |
| CoreHR TCD | 10 records, OK | **PROVISIONAL_PASS** | Same CoreHR contract; raw deadlines were present but normalization failed. |
| CoreHR Galway | 16 records, OK | **PROVISIONAL_PASS** | No source-specific failure observed; deadline extraction was weaker than other CoreHR tenants in the baseline. |
| SuccessFactors Ghent | 17 records, OK | **PROVISIONAL_PASS** | Multi-category dedup works; HTML pagination has no advertised total and metadata dates/locations are not extracted. |
| SuccessFactors VUB | 10 records, OK | **PROVISIONAL_PASS** | No source-specific failure observed; inherits shared HTML-pagination and metadata gaps. |
| SuccessFactors UCLouvain Science | 4 records, OK | **PROVISIONAL_PASS** | No source-specific failure observed; inherits shared gaps. |
| SuccessFactors University of Vienna postdoc | 23 records, OK | **PROVISIONAL_PASS** | Collector works, but the registry already warns the central University of Vienna portal is not complete for every postdoc. This is a later recall-certification issue. |
| FENS | 76 records, OK | **PROVISIONAL_PASS** | Explicit numbered-page discovery and 404-as-terminal handling are better than most HTML collectors; deadlines parsed for all baseline records. |
| ECSS | 2 records, OK | **PROVISIONAL_PASS** | Single-page board worked, but no coverage event is emitted, so current `OK` means only that the request/parser did not raise. |
| University of Innsbruck | 13 records, OK | **PROVISIONAL_PASS** | 12 FULL + 1 PARTIAL detail under current semantics; HTML completeness and role-token prefilter still need certification. |

## Systemic defects

### S1 — `FULL` does not mean Full JD

`fetch_detail_text()` and multiple source-specific collectors label a detail `FULL` whenever extracted text length is at least 200 characters. A 200-character page can be navigation, boilerplate, partial content or an error page. This status is therefore a text-length heuristic, not a completeness claim.

**Severity: MAJOR.** Stage 4 must separate `retrieved_text` from evidence-backed `full_jd_completeness`.

### S2 — date normalization is too narrow

The generic date parser accepts only a small set of exact date formats. It does not robustly handle ISO timestamps, relative Workday dates, many CoreHR formats, or current jobs.ac.uk labels. In the baseline, many otherwise successful sources had zero normalized posted/deadline dates.

**Severity: MAJOR.** This damages freshness, deadline handling and later closure/status reasoning.

### S3 — retry policy is not source-aware

The shared session retries GET only and disables `Retry-After` handling. This is particularly weak for EURAXESS 429s and means POST-based Workday/CoreHR discovery has no shared transient retry behavior.

**Severity: MAJOR.** Stage 4 should implement bounded source-specific backoff rather than one global retry policy.

### S4 — generic HTML next-link detection is too permissive

`next_listing_url()` accepts labels including `More Jobs`. That phrase is not guaranteed to mean “next page” and is a plausible cause of the observed Monash repeated-page loop.

**Severity: MAJOR.** ATS-specific pagination selectors/contracts should override the generic fallback.

### S5 — search-query matrices can create collector-level false negatives

Production LinkedIn Europe uses only `postdoctoral researcher`, `research fellow`, `assistant professor`, `lecturer`; Australia uses three of those. jobs.ac.uk uses only `postdoctoral`, `research fellow`, `lecturer`, `exercise`, `neuroscience`. Relevant families such as `research associate`, `research scientist`, `researcher`, and some domain terms can be missed before evaluation.

**Severity: MAJOR RECALL RISK.** Query taxonomy must be audited in Stage 4 and validated against ground truth later.

### S6 — long-running shards are not durable

The current main branch writes the shard bundle only after the collector returns. LinkedIn Europe was cancelled after nearly 48 minutes and produced no usable partial shard artifact.

**Severity: BLOCKER for long collectors.** Discovery progress and partial results need durable checkpoints before final certification.

### S7 — coverage evidence is inconsistent across collector families

`paginate()`-based collectors emit explicit stop evidence, but ECSS/dvs and some simple collectors do not. Therefore source-health `OK` is not semantically comparable across sources.

**Severity: MAJOR GOVERNANCE DEFECT.** Every collector must emit an explicit completeness/termination record.

### S8 — country/location correctness is not consistently source-derived

jobs.ac.uk defaults any non-Ireland parsed location to GB; AcademicPositions fixes `country_code` to the requested country board even when detail metadata may differ; academics.de uses heuristic substring inference and defaults to DE.

**Severity: MAJOR DATA-CORRECTNESS RISK.** Country must be evidence-derived with conflict diagnostics, never silently forced.

## Test-suite gaps found

The pagination regression suite correctly tests uncapped behavior, repeated-page detection, later-page failures, Workday totals, SmartRecruiters totals, PageUp next links, LinkedIn page flags and University Vacancies pages. However, it does **not** currently certify:

- EURAXESS live page semantics or 429 pacing;
- AcademicPositions terminal 404 semantics and country-slug validity;
- jobs.ac.uk country/location/date extraction;
- ECSS/dvs explicit completeness reporting;
- CoreHR/SuccessFactors completeness against a board total or independent truth set;
- `FULL` versus partial/boilerplate detail semantics;
- cancellation checkpoint recovery for long-running collectors;
- query-matrix recall.

## Stage 4 repair order produced by this audit

### P0 — discovery/correctness blockers

1. EURAXESS pagination + 429 strategy.
2. LinkedIn discovery architecture, progress and durable checkpoints; then query taxonomy.
3. AcademicPositions country routes, terminal semantics and detail failures.
4. jobs.ac.uk country/location/date parser correctness.
5. PageUp Monash pagination contract.
6. Workday Sydney total/repeated-page reconciliation.
7. Replace the global `FULL >= 200 chars` semantics.

### P1 — resilience and recall risks

8. Source-specific retry/backoff, including POST-based ATS calls.
9. Date normalization across all collectors.
10. CNRS collector-layer role prefilter review.
11. LinkedIn/jobs.ac.uk query-matrix expansion based on target-role taxonomy.
12. Explicit coverage events for ECSS/dvs and other single-page sources.

### P2 — pre-certification hardening

13. Metadata conflict diagnostics for country/location.
14. Per-source fixtures/regression tests for every defect fixed above.
15. Fresh uncapped run to prove the repaired collectors before Stage 5 observability/runtime hardening and Stage 6 board-completeness certification.

## Gate conclusion

**Phase 1 Stage 3: COMPLETE.**

**Collector certification: FAIL / NOT YET ELIGIBLE.**

No new source should be promoted yet. Stage 4 should repair the existing collection layer using the defect order above.