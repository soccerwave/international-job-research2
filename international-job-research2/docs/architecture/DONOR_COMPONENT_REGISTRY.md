# Donor Component Registry

Stage 2 establishes provenance and reuse intent. A component listed here is **not** automatically approved for production reuse; implementation-stage live validation remains mandatory.

## Donor hierarchy

Before greenfield work, inspect in order:

1. Spain production bot
2. Mads upstream
3. relevant Mads-derived regional repositories
4. other credible implementations
5. build new using the Mads portal-skill contract as a reference pattern

## A. Spain production bot

Repository: `soccerwave/researcher-job-search`

Pinned Stage 2 reference commit: `96ef9eafea2d70aaf750bcbbd69375d1bcf2eb7e`

| Component | Origin path | Reuse mode | Stage 2 decision |
|---|---|---:|---|
| LinkedIn transport | `sources/linkedin_mads.py` | `ADAPT` | Keep Mads CLI transport; redesign geographic/query configuration. |
| EURAXESS | `sources/euraxess.py` | `ADAPT` | Reuse cache/detail/rate-limit patterns; remove Spain-specific facet and card policy. |
| AcademicPositions | `sources/academicpositions.py` | `ADAPT` | Generalize country boards; preserve stable-id/JSON-LD/detail integrity patterns. |
| Teamtailor | `sources/institutions.py`, `sources/ats_watchlist.py` | `REUSE_GENERALIZE` | Proven listing/detail pattern. |
| Personio | `sources/ats_watchlist.py` | `REUSE_GENERALIZE` | XML discovery + detail-page fallback. |
| Detail fetching | `sources/fetch_detail.py` | `REUSE_OR_ADAPT` | Retry, HTML/PDF/attachment handling to be isolated from Spain assumptions. |
| De-duplication | `jobbot/dedupe.py` | `ADAPT` | Revalidate identity semantics internationally. |
| Availability | `jobbot/availability.py` | `ADAPT` | Preserve fail-open philosophy; expand languages and source-authoritative status rules. |
| State semantics | `jobbot/state.py`, `run_live_sample.py` | `ADAPT` | Preserve durable history concepts, redesign for shard fan-in. |
| Production source diagnostics | `jobbot/production.py` | `REFERENCE_PATTERN_ONLY` | Per-source fail-soft diagnostics are valuable; single mega-run topology is not reused. |
| R2 transport | `scripts/r2_store.py` | `REUSE_OR_ADAPT` | Detailed object layout deferred to Stage 8. |
| Excel reporting | `scripts/build_cloud_report.py` | `ADAPT` | International columns and queues differ. |
| Telegram resilience | `scripts/telegram_notify.py` | `REUSE_OR_ADAPT` | Keep best-effort delivery semantics. |
| Spain evaluator V1.36 | `jobbot/evaluate.py`, `jobbot/rules.py` | `DO_NOT_REUSE_AS_EVALUATOR` | International evaluator will be independently calibrated. |
| Freeze methodology | `SCORING_FREEZE_V136.json`, production integrity check | `REUSE_PATTERN` | Apply later to international evaluator and possibly other frozen components. |

### Stage 9 reporting implementation provenance

Validated implementation date: 2026-09-04.

| Local component | Origin | Reuse mode | Local changes | Validation evidence |
|---|---|---:|---|---|
| `src/reporting/report.py` | `soccerwave/researcher-job-search/scripts/build_cloud_report.py` at pinned Stage 2 commit | `ADAPT` | Removed composite-score assumptions; exposed E0.1 dimensions; added Stage 8 events, fail-open review queue, fixed seven-sheet human-review workbook, and country-as-dimension policy. | GitHub Actions run `33910435658`; smoke artifact `9951132980`. |
| `src/reporting/telegram.py` | `soccerwave/researcher-job-search/scripts/telegram_notify.py` at pinned Stage 2 commit | `ADAPT` | Preserved retry/permanent-vs-transient delivery semantics; changed message to international academic recommendations, Stage 8 events, review queue, and source health. | 12 Stage 9 unit tests in run `33910435658`; live delivery remains a separate acceptance gate. |

These donor components are from the user's own Spain production repository. No third-party source code or new external license obligation was introduced by the Stage 9 adaptation.

## B. Mads upstream

Repository: `MadsLorentzen/ai-job-search`

Pinned reference commit: `fd89eac178dc546d41f6c1a3213de88d96112c6d`

License at pinned reference: MIT.

| Component | Origin path | Reuse mode | Notes |
|---|---|---:|---|
| Country-agnostic portal generator | `.claude/commands/add-portal.md` | `REFERENCE_PATTERN_ONLY` | Mandatory reconnaissance -> scaffold -> live search/detail -> tests workflow. |
| LinkedIn CLI | `.agents/skills/linkedin-search/` | `REUSE_VIA_EXISTING_SPAIN_ADAPTER` | Already integrated indirectly by the Spain bot. |
| Portal CLI contract | `.agents/skills/*/cli/` conventions | `REFERENCE_PATTERN_ONLY` | Search/detail commands, JSON output, stderr errors, retry/backoff, low-volume live tests. |
| Dynamic portal CI concept | upstream CI / add-portal workflow | `REFERENCE_PATTERN_ONLY` | New adapters should join checks without bespoke CI wiring where practical. |

MIT obligations must be preserved if substantial source code is copied or modified.

## C. Mads-derived Germany / US repository

Repository: `SentImperior666/ai-job-search-de-us`

Pinned reference commit: `1fb2b17c4c2d83028926a3cc051dfdc4aca34316`

License at pinned reference: MIT notice naming Mads Lorentzen.

| Component | Origin path | Reuse mode | Notes |
|---|---|---:|---|
| Generic ATS roster pattern | `.agents/skills/ats-search/` | `REFERENCE_PATTERN_HIGH_VALUE` | Config-driven multi-tenant pattern, full JD, fail-soft per company. |
| Greenhouse adapter | `.agents/skills/ats-search/` | `REUSE_IF_NEEDED_AFTER_LIVE_VALIDATION` | Not currently a core-market requirement, but mature example. |
| Ashby adapter | `.agents/skills/ats-search/` | `REUSE_IF_NEEDED_AFTER_LIVE_VALIDATION` | Same. |
| Lever adapter | `.agents/skills/ats-search/` | `REUSE_IF_NEEDED_AFTER_LIVE_VALIDATION` | Same. |
| Germany portals | `.agents/skills/stepstone-search/`, `arbeitsagentur-search/`, etc. | `AUDIT_BEFORE_USE` | Potential extra coverage; not automatically promoted into V1 source scope. |

## D. Mads-derived UK repository

Repository: `anjolok1997/ai-job-search-uk`

Pinned reference commit: `d1747069a5a9e69f0d11894cc99719efb34a1f19`

| Component | Origin path | Reuse mode | Notes |
|---|---|---:|---|
| Reed | `.agents/skills/reed-search/` | `DEFER` | General job market; not a primary academic source. |
| Totaljobs | `.agents/skills/totaljobs-search/` | `DEFER` | Same. |
| Welcome to the Jungle | `.agents/skills/wttj-search/` | `DEFER` | Same. |
| Dynamic portal discovery in CI | repository CI at pinned commit | `REFERENCE_PATTERN_ONLY` | Useful for Stage 4 CI design. |

## Provenance fields for future copied/adapted components

Every imported donor component must record at least:

```yaml
origin_repo: owner/repository
origin_path: path/in/origin
origin_commit: full_sha
reuse_mode: COPY_AS_IS | ADAPT | REWRITE_FROM_PATTERN
license: SPDX-or-note
local_changes: short description
validated_on: YYYY-MM-DD
validation_evidence: test/live replay reference
```
