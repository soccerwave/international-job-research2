## International automation correction — 2026-09-06

- The shared Cloudflare control plane now sends `max_jobs_per_source=all` for
  International manual and scheduled runs, replacing its stale explicit `20`.
- Daily dispatch moves to Cloudflare at 06:00 Europe/Madrid with DST-aware routing.
- Remove the duplicate 06:17 UTC native GitHub cron after Worker deployment.

## V1.1_PAGINATED_DISCOVERY — 2026-09-06

- Remove the production 20-record clamp and first-page search limits; default to `all`.
- Keep the historical Stage 10 probe policy intact; production has its own source map.
- Add native Workday, SmartRecruiters, University Vacancies and LinkedIn pagination;
  follow HTML next-page links for PageUp, CoreHR, SuccessFactors and direct portals.
- Paginate each EURAXESS/AcademicPositions country and jobs.ac.uk query independently.
- Preserve earlier records after later-page errors; report truncated/repeated/failed
  discovery as PARTIAL, with page counts and stop reasons in source diagnostics.
- Ignore malformed Retry-After headers while retaining bounded retry/backoff behavior.
- Preserve the V1.0 freeze as historical evidence; V1.1 has a separate integrity manifest.
- Evaluator, canonical identity, durable state and Telegram routing remain unchanged.

# Changelog

All architecture, source, evaluator, state, and production changes must be versioned and recorded here.

## V1.0_VALIDATED_OPERATIONAL_INTERNATIONAL_PIPELINE — 2026-09-05

### Operational release

- Promoted the international academic job-search pipeline from release candidate to accepted V1 production.
- Production uses 14 independent collection shards, one central finalizer, authoritative Cloudflare R2 state at `state/current/state.json`, seven-sheet Excel reporting, Telegram delivery, guarded scheduling, and CAS-safe recovery.
- The first complete production inventory is preserved as `BASELINE_EXISTING` for reporting so the initial market snapshot is visible without being falsely reported as today's new vacancies.
- Subsequent production runs use normal `NEW`, `SEEN`, `MATERIALLY_CHANGED`, and `REOPENED` semantics.

### Fixed during final live acceptance

- The first production attempt (`33925571876`) failed safely in readiness because `jsonschema` was absent from the production state-job dependency contract; no shard or authoritative state write was reached. Production/recovery dependency installation was aligned with the tested runtime contract.
- The first successful bootstrap (`33927872040`) established generation 1 and baseline reporting, but revealed that strict preflight and the frozen Stage 4 finalizer consumed identical immutable shards in different orders. Because the frozen Stage 10 canonicalizer is greedy, preflight produced 518 canonical vacancies while the core produced 522.
- Without modifying frozen Stage 7–10 behavior, the V1 guard layer was changed so strict preflight consumes shard directories in the exact sorted order used by the finalizer, rejects unexpected shard directories, and requires both canonical count equality and an order-independent canonical-ID SHA-256 match before certification.

### Final acceptance

- Final strict production acceptance run: `33928709517` — PASS.
- Production run ID: `prod-33928709517-1`.
- Accepted behavior commit: `8390fbc5b32b91fbdadc0d443c44e414e2053922`.
- Expected/present shards: 14/14; rejected: 0; missing: 0; unexpected: 0.
- Source health: 29 OK, 0 PARTIAL, 0 ERROR, 0 UNKNOWN.
- Records loaded: 548; canonical/evaluated: 522/522; duplicates removed: 26.
- Strict preflight canonical count: 522; core canonical count: 522.
- Canonical-ID digest matched exactly: `8abbd591c783eabbd8dbc8f6eb3226298f72d29c83e6dd55398196010ae8ef52`.
- Authoritative R2 state advanced from generation 1 to generation 2 with 547 historical state jobs.
- Current run events: 25 NEW, 497 SEEN, 0 materially changed, 0 reopened, 0 inferred closures.
- Reporting: 447 current actionable, 23 today actionable, 390 review queue, 7 low priority, 66 skipped.
- Telegram configuration and strict delivery: PASS.
- Final production artifact ID: `9957801900`.
- Artifact digest: `sha256:7e1e5780453589abcf5be92d53a6b789da86961746f05bf68268a6aa06eb89a9`.
- Production workbook independently reopened and verified: seven expected sheets, `TODAY_ACTIONABLE=23`, `CURRENT_ACTIONABLE=447`, `AUDIT=522`, and zero formula-error tokens.
- Final deterministic V1 CI on accepted behavior commit: run `33928546290` — PASS.
- V1 tests: 18 PASS; Stage 10: 13; Stage 9: 12; Stage 8: 29; Stage 7: 24; Stage 6: 21; Stage 5: 11; Stage 4: 4; total unittest methods: 132 PASS.
- Stage 7, Stage 8, Stage 9, Stage 10, and V1 freeze verification: PASS.
- Release freeze status: `ACCEPTED`.

## V0.10_PREPROD_RC1 — 2026-09-04

### Added

- End-to-end pre-production integration from 14 independent live collection shards through Stage 4 fan-in, conservative canonicalization, evaluator `E0.1`, finalizer-only durable state, isolated Cloudflare R2 CAS persistence, and `REPORTING_V1.0.0` Excel output.
- Pre-production contract `PREPROD_RC1_CONTRACT_V1.0.0`.
- Conservative cross-source canonicalization with unresolved fuzzy merging disabled under the recall-first policy.
- Stage-only state identity projection that removes URL aliases only when the same URL is shared by distinct canonical vacancies, while leaving canonical/reporting URLs untouched.
- Pre-publish state-alias collision detection and state-cardinality checks.
- Exact R2 replay verification requiring the same canonical dataset to become entirely `SEEN` without spurious material changes.
- Explicit missing-shard and degraded-source handling so incomplete collection surfaces as `PARTIAL_PASS` and never implies closure.
- Strict acceptance gate requiring zero missing shards, zero degraded sources, zero UNKNOWN source-health entries, positive canonical count, one durable state identity per canonical record, zero inferred closures, and a successful exact replay.
- Stage 10 regression coverage for canonicalization, failure injection, missing shards, repeated board-level URL aliases, and LinkedIn source-health key consistency.
- Stage 10 freeze manifest `PREPROD_FREEZE_V1.0.0.json` protecting 13 behavior-defining Git blobs plus an independent freeze verifier enforced by CI.
- Independent Stage 10 acceptance record under `docs/runtime/STAGE10_ACCEPTANCE.md`.

### Fixed during live acceptance

- Initial live shadow run `33917037095` revealed a durable-state identity collision: 106 unique canonical vacancies collapsed into 41 state entries because repeated board-level listing/detail/apply URLs were accepted as aliases. The run correctly failed replay validation.
- The collision was fixed without modifying the frozen Stage 8 state engine. Stage 10 now projects state identity separately, suppresses repeated URL aliases only for state matching, rejects remaining alias collisions before publish, and verifies state cardinality against the canonical record count.
- Follow-up shadow run `33918314776` passed state identity and replay but exposed `source_health UNKNOWN=1` because LinkedIn records emitted `source_key=linkedin_mads` while Stage 10 diagnostics used `report_key=linkedin`.
- LinkedIn diagnostics were aligned to `linkedin_mads`, a regression was added, and strict acceptance was hardened to reject any nonzero UNKNOWN source-health count.

### Acceptance

- Final strict live acceptance run: `33920081869` — PASS.
- Strict-run behavior commit: `cc9452bbb1fc4e8443116c0bee85b50f6848fb3f`.
- Expected/accepted shards: 14/14; rejected: 0; missing: 0.
- Records loaded/canonical/evaluated: 106/106/106.
- Source health: 29 OK, 0 PARTIAL, 0 ERROR, 0 UNKNOWN.
- Fresh isolated R2 generation: 106 NEW, 106 state jobs, 0 material changes, 0 reopened, 0 inferred closures.
- Exact replay generation: 106 SEEN, 0 NEW, 0 material changes, 0 reopened, 0 inferred closures.
- Remaining cross-record identity collisions: 0; unique state IDs: 106.
- Strict R2 prefix: `acceptance/stage10/stage10-33920081869-1`; production `state/current/state.json` was not touched.
- Strict evidence artifact ID: `9954794109`.
- Artifact digest: `sha256:fa554a16cdebbd547b682c50849be63867594456b9398e5d4b57337e382cc56d`.
- Workbook independently reopened with all seven fixed reporting sheets and zero formula-error tokens.
- Stage 10 tests: 13 PASS.
- Stage 9 regression tests: 12 PASS.
- Stage 8 regression tests: 29 PASS.
- Stage 7 regression tests: 24 PASS.
- Stage 6 regression tests: 21 PASS.
- Stage 5 regression tests: 11 PASS.
- Stage 4 regression tests: 4 PASS.
- Total unittest methods in the Stage 10 gate: 114 PASS.
- Stage 7, Stage 8, Stage 9, and Stage 10 freeze verifiers: PASS.
- Pre-production freeze status: `ACCEPTED`.

### Explicitly not implemented

- No production scheduler activation yet.
- No writes to the production R2 state key during Stage 10 acceptance.
- No final `V1.0_VALIDATED_OPERATIONAL_INTERNATIONAL_PIPELINE` release certification yet.

## V0.9_REPORTING — 2026-09-04

### Added

- Reporting baseline `REPORTING_V1.0.0` for canonical, evaluated, Stage-8-state-annotated vacancies.
- Human-review-first XLSX generation with seven fixed sheets: `SUMMARY`, `TODAY_ACTIONABLE`, `CURRENT_ACTIONABLE`, `REVIEW_QUEUE`, `LOW_PRIORITY`, `AUDIT`, and `SOURCES`.
- Country retained as a reporting dimension rather than creating a sheet per country.
- Stage 7 multidimensional evaluator output preserved directly in reporting; no composite reporting score was introduced.
- `CURRENT_ACTIONABLE` for open `STRONG_APPLY`, `APPLY`, and `REVIEW` vacancies.
- `TODAY_ACTIONABLE` restricted to actionable `NEW`, `MATERIALLY_CHANGED`, and `REOPENED` state events.
- Fail-open `REVIEW_QUEUE` preserving ambiguous roles, policy reviews, and unresolved Full JD cases for human inspection.
- Source-health reporting and an audit sheet that retains lower-priority and skipped records for traceability.
- Telegram reporting with compact decision-oriented summaries, optional XLSX attachment, transient retry handling, and explicit permanent-configuration errors.
- Stage 9 reporting regression suite, deterministic XLSX/Telegram smoke, freeze verifier, and `REPORTING_FREEZE_V1.0.0.json` protecting 11 behavior-defining files.
- Reporting dependency pin `XlsxWriter==3.2.5`.
- Stage 9 reporting contract and acceptance documentation under `docs/reporting/`.

### Reporting decisions

- Reporting consumes Stage 8 state annotations and never recomputes or mutates durable state.
- Telegram is downstream of state persistence; a Telegram failure cannot roll back or invalidate a successful R2 state write.
- `SKIP` remains visible in audit reporting rather than disappearing from traceability.
- Missing detail and policy ambiguity remain reviewable according to the frozen fail-open policy.
- The Spain reporting implementation was adapted as a donor pattern, but the Spain composite-score presentation was not reused.

### Fixed during acceptance

- The first Stage 9 deterministic smoke exposed the same direct-script import-path class seen in Stage 8: `python scripts/run_stage9_smoke.py` could not import `src` from the scripts directory.
- All Stage 9 command-line scripts now add the repository root to `sys.path` when executed directly.
- Freeze verification was added to the Stage 9 workflow before acceptance.

### Acceptance

- Deterministic pre-freeze reporting run: `33910831069` — PASS.
- Final live Telegram acceptance run: `33913219057` — PASS.
- Commit validated by the live Telegram acceptance: `e329832c2c06ac97f0184e0c755f20aa32166daa`.
- Final deterministic artifact ID: `9952148653`.
- Artifact SHA-256: `5262c50a1800e3f75e96fd3a4ffee4c2ef2e8bc6f162a2601ff45eb151967024`.
- Telegram configuration validation: PASS.
- Telegram message delivery: PASS.
- XLSX document delivery: PASS.
- Configured Telegram chat count during acceptance: 2.
- Stage 9 tests: 12 PASS.
- Stage 8 regression tests: 29 PASS.
- Stage 7 regression tests: 24 PASS.
- Stage 6 regression tests: 21 PASS.
- Stage 5 regression tests: 11 PASS.
- Stage 4 regression tests: 4 PASS.
- Total unittest methods in the Stage 9 gate: 101 PASS.
- Stage 7 freeze verifier: PASS.
- Stage 8 freeze verifier: PASS.
- Stage 9 freeze verifier: PASS with 11 protected Git blobs and zero mismatches.
- Reporting freeze status: `ACCEPTED`.

### Explicitly not implemented

- No production scheduler yet.
- No integrated end-to-end production runner yet.
- No Stage 10 shadow-run or failure-injection certification yet.
- No V1.0 production release certification yet.

## V0.8_STATE_PERSISTENCE — 2026-09-04

### Added

- Durable state schema `STATE_SCHEMA_V1.0.0` with explicit `NEW`, `SEEN`, `MATERIALLY_CHANGED`, and `REOPENED` events.
- Separate Full-JD quality events `DETAIL_RESOLVED` and `DETAIL_UNRESOLVED` so detail-fetch degradation does not masquerade as a vacancy change.
- Conservative identity aliases with an explicit prohibition on fuzzy cross-source state merging.
- `CENTRAL_FINALIZER` as the only supported durable-state writer role.
- Local atomic state writes and corruption/version rejection.
- Cloudflare R2 S3-compatible persistence with immutable generation backups, SHA-256 metadata/read-back integrity verification, and ETag compare-and-swap semantics.
- First-write protection with `If-None-Match: *` and subsequent writes with `If-Match: <previous ETag>`.
- `FinalizerStateWriter` boundary kept separate from the Stage 4 raw fan-in finalizer until canonicalization/evaluation integration is ready.
- Stage 8 regression suites for state semantics, R2 transport/CAS behavior, and finalizer-writer ownership.
- Stage 8 freeze manifest `STATE_FREEZE_V1.0.0.json` protecting 13 behavior-defining files.
- Isolated live-R2 acceptance profile `STAGE8_R2_LIVE_CAS` under `acceptance/stage8/<run-id>/`, leaving the production `state/current/state.json` key untouched during acceptance.

### State decisions

- Absence from a later run never implies closure.
- A failed or missing shard never implies closure.
- `UNKNOWN` or `ERROR` source status never becomes closed.
- `REOPENED` requires prior explicit `CLOSED` evidence followed by explicit `OPEN` evidence.
- Full-JD degradation does not overwrite the last trustworthy enriched snapshot.
- Identity conflicts fail the write rather than silently merging histories.
- Generic careers/listing URLs are excluded from durable identity aliases after regression testing exposed a false-merge risk for distinct vacancies sharing the same title and listing page.
- The Stage 4 raw fan-in finalizer remains intentionally unwired to durable state until canonicalization/evaluation integration is completed.

### Fixed during acceptance

- A false-merge identity bug was found and fixed: two distinct vacancies sharing a generic careers listing URL and title can no longer collapse into one state entry.
- The first manual R2 acceptance attempt (`33907625254`) was invalid even though GitHub displayed the job as green: `run_stage8_r2_smoke.py` failed to import `src`, while `tee` masked the Python exit code.
- The smoke script now adds the repository root to its import path when executed directly from `scripts/`.
- The live acceptance step now uses `set -euo pipefail`, so a failing Python process cannot be hidden by `tee`.
- Cloud transport dependencies were pinned exactly: `boto3==1.43.88`, `botocore==1.43.88`, `s3transfer==0.19.2`.

### Acceptance

- Pre-freeze state regression run: `33906803021` — PASS.
- Freeze-candidate verification run after the live-gate fix: `33907964795` — PASS.
- Final valid live Cloudflare R2 acceptance run: `33908172065` — PASS.
- Valid live acceptance commit: `b67a7c449127d1757614fa3708fbb0dd7c9864a7`.
- Live acceptance prefix: `acceptance/stage8/33908172065-1`.
- Live acceptance artifact ID: `9950302267`.
- Live bootstrap write: PASS.
- Conditional generation-1 write: PASS.
- Conditional generation-2 write: PASS.
- Immutable backup creation: PASS.
- SHA-256/read-back integrity: PASS.
- Stale-writer rejection: PASS (`stale_writer_rejected=true`).
- Final acceptance state: generation `2`, jobs `1`.
- Stage 8 tests: 29 PASS.
- Stage 7 regression tests: 24 PASS.
- Stage 6 regression tests: 21 PASS.
- Stage 5 regression tests: 11 PASS.
- Stage 4 regression tests: 4 PASS.
- Total unittest methods in the Stage 8 gate: 89 PASS.
- Evaluator freeze verifier: PASS.
- Stage 8 freeze verifier: PASS with 13 protected Git blobs and zero mismatches.

### Explicitly not implemented

- No Stage 9 Excel/Telegram reporting yet.
- No production scheduling yet.
- No Stage 10 pre-production/shadow-run validation yet.
- No automatic wiring of raw shard fan-in directly into durable state before canonicalization/evaluation integration.

## V0.7_EVALUATOR_BASELINE — 2026-09-04

### Added

- International evaluator baseline `E0.1` with a dedicated output schema and no single composite score.
- Seven independent evaluation dimensions: scientific fit, career level, methods, language, mobility, professional registration, and contract.
- Evidence-bounded routing to `STRONG_APPLY`, `APPLY`, `REVIEW`, `LOW_PRIORITY`, or `SKIP`.
- Fail-open handling for missing Full JD, ambiguous role level, unclear local titles, sponsorship silence, uncertain mobility, and preferred methods.
- Explicit hard-blocker handling for student/doctoral roles, French MCF faculty, mandatory professional registration, mandatory medical/nursing degree, German C1/C2 required for teaching, mandatory patch clamp/optogenetics/specialist wet-lab work, advanced AI/ML requirements, and the configured Australian no-sponsorship plus existing-work-rights case.
- Explicit protection against inferring advanced independent fMRI analysis from MRI/neuroimaging exposure.
- Cross-market calibration fixture covering 16 cases across the Netherlands, Germany, Ireland, the United Kingdom, Belgium, France, Australia, Austria, and Luxembourg.
- Secondary-role regression coverage for Research Scientist, Scientific Project Manager, Research Project Manager, and Research Programme Manager.
- Evaluator freeze manifest `EVALUATOR_FREEZE_E0.1.json` plus independent Git-blob verification for 16 behavior-defining files.
- Stage 7 CI gate running evaluator, Stage 6, Stage 5, and Stage 4 regressions together.

### Policy mapping update

- Role policy mapping advanced from `ROLE_POLICY_V1.0.0` to `ROLE_POLICY_V1.0.1` to add the already-declared secondary title families for scientific/research project and programme managers. This did not enable secondary roles for automatic apply routing; they remain `REVIEW` by default.

### Calibration decisions

- Spain V1.36 composite scoring was not reused. Only evidence hygiene plus regression/freeze discipline were carried forward.
- `SKIP` is produced only by explicit configured hard-blocker evidence; a weak fit without a hard blocker is not silently converted into a skip.
- Missing or failed Full JD remains `REVIEW` / `NEEDS_DETAIL_REVIEW`.
- A United Kingdom posting that explicitly says sponsorship is unavailable remains `REVIEW`, not `SKIP`, because mobility is evaluated separately from scientific fit.
- Australian sponsorship silence remains `REVIEW`. The calibration case for a casual Australian lecturer therefore remains `REVIEW` rather than being forced to `LOW_PRIORITY`; a separate senior-professor case preserves low-priority calibration coverage.
- Mandatory advanced independent fMRI preprocessing/analysis routes to `REVIEW` because the declared profile establishes MRI/neuroimaging exposure and collaboration, not advanced independent analysis.
- Preferred MRI remains non-blocking.
- Generic Research Fellow and uncertain postdoctoral-level local titles remain `REVIEW`.

### Acceptance

- Pre-freeze regression run: `33904441665` — PASS.
- Freeze candidate verification run: `33904599196` — PASS.
- Final accepted freeze run: `33904691713` — PASS.
- Validated accepted-freeze commit: `618da79cda010196f9e0a01c57855f4c19fdf853`.
- Stage 7 rule tests: 20 PASS.
- Stage 7 secondary role-mapping tests: 3 PASS.
- Cross-market calibration: 16/16 expected cases PASS.
- Calibration distribution: 5 `STRONG_APPLY`, 2 `APPLY`, 7 `REVIEW`, 1 `LOW_PRIORITY`, 1 `SKIP`.
- Stage 6 regression tests: 21 PASS.
- Stage 5 regression tests: 11 PASS.
- Stage 4 runtime regression tests: 4 PASS.
- Total unittest methods in the final Stage 7 gate: 60 PASS.
- Evaluator freeze verifier: PASS with 16 protected Git blobs and zero mismatches.

### Explicitly not implemented

- No Stage 8 persistent NEW/SEEN/changed/reopened state engine.
- No R2 persistence implementation.
- No Stage 9 Excel/Telegram reporting.
- No production scheduler or Stage 10+ pre-production work.

## V0.6_CORE_MARKET_COVERAGE — 2026-09-04

### Added

- Final core-market source registry `CORE_SOURCE_REGISTRY_V1.0.0`.
- Primary/direct collectors for AcademicTransfer, academics.de, University Vacancies Ireland, CNRS Emploi, and the University of Innsbruck.
- Generic CoreHR adapter for UCD, DCU, UCC, Trinity College Dublin, and University of Galway.
- Generic PageUp adapter for Monash, Deakin, and UNSW.
- Generic SmartRecruiters adapter for Western Sydney University and Griffith University using the public postings API.
- Generic SuccessFactors coverage for Ghent University, VUB, UCLouvain scientific staff, and University of Vienna postdoctoral jobs.
- Generic Workday CXS coverage for the University of Queensland, Flinders University, and the University of Sydney.
- Dedicated University Vacancies Ireland API adapter using `/api/job-posts/public`, including Full JD HTML directly from the listing payload.
- Full configured ATS tenant-matrix acceptance covering 17 tenants across five ATS families.
- Stage 6 regression coverage for shared HTML detail extraction, including empty semantic roots and form-wrapped job content.
- Stage 6 workflow coverage for changes to shared detail extraction and the tenant-matrix script.

### Fixed during acceptance

- University Vacancies Ireland was migrated from the dynamic HTML frontend to its public JSON API; upstream `published` state is normalized to the canonical source-status contract.
- CoreHR now selects the actual recruitment search form rather than a preceding login form.
- CoreHR supports current `javascript:viewTheJobSpec(...)` vacancy links as well as direct detail links.
- CoreHR detail parsing can recover a fuller vacancy title when the listing anchor is truncated; live Galway validation upgraded `Professor In` to `Professor In Pharmacy`.
- PageUp UNSW was corrected to tenant `841`.
- Generic HTML detail extraction now falls back from empty semantic roots to body content and preserves useful content wrapped by form elements; this restored Deakin Full JD extraction.
- Ghent SuccessFactors coverage now aggregates the real Research staff, Assistant academic staff, and Professorial staff category pages rather than the empty landing page.
- academics.de no longer assumes every listing is German when explicit foreign-country evidence is present; live validation preserved a Hainan (China) vacancy as `CN` rather than `DE`.
- Acceptance diagnostics used to investigate Deakin and Galway were removed before the Stage 6 freeze.

### Acceptance

- Final live acceptance run: `33902955030`.
- Validated freeze commit: `7cdb742aa61efc609c7a21d2e2a90208765aff77`.
- Final representative validation profile: `STAGE6_FINAL_CORE_MARKET_COVERAGE` — PASS.
- ATS tenant matrix: 17/17 PASS, 0 failures; all 17 acceptance tenant samples returned `FULL` detail status.
- Stage 6 parser/schema/detail-extraction tests: PASS.
- Stage 5 regression tests: PASS.
- Stage 4 runtime regression tests: PASS.
- AcademicTransfer, academics.de, University Vacancies Ireland, CoreHR UCC, CNRS Emploi, PageUp Monash, SmartRecruiters Western Sydney, SuccessFactors VUB, Workday UQ, and University of Innsbruck representative probes passed the final live gate.
- University of Innsbruck representative detail was accepted as `PARTIAL` under the existing fail-open detail contract.
- UniRoles Australia is explicitly `DEFER_BLOCKED_ON_GITHUB_RUNNER`: listing, legacy listing, and sitemap requests are Cloudflare-blocked with HTTP 403 on GitHub-hosted runners; search/action/RSS/feed routes are also disallowed by its robots policy. Australia remains independently covered by PageUp, SmartRecruiters, and Workday.

### Explicitly not implemented

- No Stage 7 scientific evaluator or scoring baseline.
- No persistent NEW/SEEN/changed/reopened state engine.
- No R2 persistence implementation.
- No Excel/Telegram reporting or production scheduler.
- No Stage 8+ state/reporting work was started during Stage 6 acceptance.

## V0.5_SHARED_COVERAGE — 2026-09-04

### Added

- Shared-source registry `SHARED_SOURCE_REGISTRY_V1.0.0`.
- Live collectors for EURAXESS, Academic Positions, LinkedIn, jobs.ac.uk, ECSS Vacancies, dvs Stellenbörse, and FENS Job Market.
- Source-local Full JD retrieval across HTML, JSON-LD, PDF, and the pinned Mads LinkedIn detail transport.
- Pinned Python dependencies for requests, Beautiful Soup, pypdf, and JSON Schema validation.
- Stage 5 parser/schema regression tests and low-volume live-smoke validation workflow.
- Explicit donor provenance for adapted Spain collectors and the pinned Mads LinkedIn implementation.
- Donor-audit records for jobs.ac.uk, ECSS, dvs, and FENS before greenfield implementation.

### Fixed during acceptance

- EURAXESS was migrated from the legacy Spain facet assumption to the current dynamically discovered `job_country[]` values and stable GET facets; silent global fallback was removed.
- Generic EURAXESS detail headings such as `Job offer` no longer replace actual vacancy titles.
- EURAXESS country-facet provenance is stored per record rather than leaking the final loop facet across records.
- dvs country metadata is inferred only from explicit domain/text evidence instead of assuming every dvs vacancy is German.
- FENS country metadata now preserves Hong Kong as `HK` while leaving its market tier outside configured target markets.
- Empty FENS department fields no longer absorb the following Description field.

### Acceptance

- Final live acceptance run: `33895687778`.
- Validated commit: `f6d622c85d9d3288df2aaff2d141d8b6c2c72c7a`.
- Stage 5 parser/schema tests: PASS.
- Stage 4 regression tests: PASS.
- Seven-source live discovery: PASS.
- Seven-source sample Full JD retrieval: PASS (`FULL` for every acceptance sample).
- Strict country checks passed for EURAXESS Germany, Academic Positions Germany, jobs.ac.uk United Kingdom, and LinkedIn Germany; ECSS, dvs, and FENS also preserved source-supported country metadata.

### Explicitly not implemented

- No Stage 6 country-primary portals or ATS families.
- No cross-source canonical identity/deduplication.
- No Stage 7 scientific evaluator.
- No persistent NEW/SEEN/changed/reopened state.
- No R2 persistence.
- No Excel/Telegram reporting or production scheduler.

## V0.4_SHARDED_RUNTIME — 2026-09-04

### Added

- Independent Python shard runner boundary.
- Immutable per-run/per-shard artifact layout with `records.json`, `diagnostics.json`, and `manifest.json`.
- `SHARD_ARTIFACT_CONTRACT_V1.0.0`.
- SHA-256 integrity verification for records and diagnostics.
- Atomic no-clobber publication for immutable local artifacts.
- Fail-soft shard execution that converts collector exceptions into `ERROR` bundles instead of aborting unrelated shards.
- Central Stage 4 fan-in finalizer with `FINALIZER_FANIN_CONTRACT_V1.0.0`.
- Partial-run semantics: healthy shards can be accepted while failed/corrupt shards are rejected.
- Runtime fixtures for successful and intentionally failing shards.
- Unit tests for successful fan-in, failed-shard isolation, immutable artifact protection, and checksum corruption rejection.
- Stage 4 smoke test.
- GitHub Actions test-only workflow for Python 3.12 runtime validation.

### Fixed during acceptance

- Smoke script import path was made independent of how the script is invoked.
- Artifact publication was hardened from check-plus-replace to atomic no-clobber publication to eliminate an overwrite race.
- Manifest artifact paths are fixed to contract-owned filenames and mutable bundles are rejected.

### Explicitly not implemented

- No production job collector or ATS adapter.
- No cross-source identity canonicalization or deduplication.
- No scientific evaluator.
- No mobility/language evaluator execution.
- No NEW/SEEN or closure state logic.
- No R2 persistence.
- No Excel/Telegram reporting or production scheduler.

## V0.3_DATA_POLICY_CONTRACT — 2026-09-04

### Added

- Canonical vacancy schema `VACANCY_SCHEMA_V1.0.0`.
- Market policy for core, opportunistic, and excluded countries.
- Normalized role families and country-specific academic-title mappings.
- Evidence-bounded scientific profile plus explicit `do_not_infer` constraints.
- Fail-open language policy.
- Mobility routing policy kept separate from scientific fit.
- Explicit hard blockers and review triggers.
- Pre-evaluation dispositions: `ELIGIBLE_FOR_EVALUATION`, `NEEDS_DETAIL_REVIEW`, `POLICY_REVIEW`, and `POLICY_SKIP`.
- Valid sample vacancy fixture.
- Official mobility-reference document.
- Stage 3 acceptance contract and freeze boundary.

### Policy decisions frozen

- Missing Full JD never causes direct skip.
- Sponsorship silence never causes direct skip.
- Preferred MRI is not a blocker.
- France faculty remains out of initial scope.
- Explicit German C1/C2 required for teaching is a hard blocker under the current profile policy.
- Australia is blocked only when the posting explicitly states no sponsorship and requires existing work rights.
- Secondary Research Scientist / scientific-project-management role families remain disabled by default pending intentional activation.

### Explicitly not implemented

- No production collectors or ATS adapters.
- No Stage 7 scientific evaluator.
- No state engine or R2 persistence implementation.
- No reporting engine or scheduler.

## V0.2_ARCHITECTURE_BASELINE — 2026-09-04

### Added

- Independent repository architecture baseline.
- One-codebase / independent-collection-shards / central-finalizer topology.
- Central-finalizer-only shared-state write rule.
- Hybrid Python 3.12 + Bun/TypeScript runtime decision.
- Donor-first engineering policy covering the Spain production bot, Mads upstream, and regional Mads derivatives.
- Donor component provenance registry with pinned reference commits.
- Stage 1 feasibility audit summary.
- Architecture decision records for repository separation, sharding, state ownership, and runtime boundaries.

### Explicitly not implemented

- No production collectors.
- No ATS adapters.
- No international evaluator.
- No canonical vacancy schema.
- No R2 state implementation.
- No Excel or Telegram implementation.
- No production workflows or scheduler.

## V0.1_FEASIBILITY_AUDIT — 2026-09-04

### Completed

- Audited core-market source strategy.
- Identified reusable Spain components.
- Identified Mads ecosystem as an explicit donor source.
- Prioritized generic ATS families including CoreHR, PageUp, SmartRecruiters, SuccessFactors, and Workday.
- Proposed initial collection-shard topology.
