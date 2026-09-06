# Stage 10 Pre-production RC1 Acceptance

Status: **ACCEPTED**

Pipeline stage: `V0.10_PREPROD_RC1`

Contract: `PREPROD_RC1_CONTRACT_V1.0.0`

Freeze manifest: `PREPROD_FREEZE_V1.0.0.json`

## Strict live acceptance

- Workflow run: `33920081869`
- Behavior commit: `cc9452bbb1fc4e8443116c0bee85b50f6848fb3f`
- Profile: `STAGE10_PREPROD_RC1_STRICT_LIVE`
- Preprod artifact: `9954794109`
- Artifact digest: `sha256:fa554a16cdebbd547b682c50849be63867594456b9398e5d4b57337e382cc56d`
- R2 prefix: `acceptance/stage10/stage10-33920081869-1`
- Production state touched: **no**

## Collection and fan-in

- Expected shards: 14
- Accepted shards: 14
- Rejected shards: 0
- Missing shards: 0
- Records loaded: 106
- Records emitted: 106
- Degraded sources: 0
- Source health: 29 OK, 0 PARTIAL, 0 ERROR, 0 UNKNOWN

## Canonicalization and evaluation

- Canonical input records: 106
- Canonical records: 106
- Evaluated records: 106
- Unresolved fuzzy cross-source merge: disabled
- Remaining cross-record state-identity collisions: 0
- Unique state IDs observed: 106
- Canonical records mutated by state projection: no

The Stage 10 state-only identity projection suppresses repeated URL aliases only for durable-state matching when the same URL occurs across distinct canonical vacancies. Human-facing canonical records and URLs remain unchanged.

## Fresh durable-state generation

Generation 1:

- NEW: 106
- SEEN: 0
- MATERIALLY_CHANGED: 0
- REOPENED: 0
- State jobs: 106
- Records observed: 106
- Absence inferred closed: 0
- Writer role: `CENTRAL_FINALIZER`
- Backend: `CLOUDFLARE_R2_CAS`

## Exact replay

Generation 2:

- NEW: 0
- SEEN: 106
- MATERIALLY_CHANGED: 0
- REOPENED: 0
- State jobs: 106
- Records observed: 106
- Absence inferred closed: 0

The replay therefore demonstrates idempotent observation of the exact same canonical dataset across consecutive R2 generations.

## Reporting evidence

The strict-run workbook was independently reopened after artifact download.

Expected sheets were present:

- `SUMMARY`
- `TODAY_ACTIONABLE`
- `CURRENT_ACTIONABLE`
- `REVIEW_QUEUE`
- `LOW_PRIORITY`
- `AUDIT`
- `SOURCES`

No `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, or `#N/A` formula-error tokens were found during the independent workbook check.

Strict-run reporting counts:

- Records observed: 106
- Current actionable: 87
- Today actionable: 87
- Review queue: 69
- Low priority: 2
- Skipped: 15
- APPLY: 18
- REVIEW: 71
- STRONG_APPLY: 0

These counts describe the low-volume Stage 10 live acceptance probe and are not a production market census.

## Incidents discovered and closed during Stage 10

### State identity collision

Initial live shadow run `33917037095` accepted all 14 shards and produced 106 canonical records, but repeated board-level URL aliases collapsed those records into 41 durable state entries. The run correctly failed replay acceptance.

Resolution: a state-only identity projection now removes URL aliases that repeat across distinct canonical records. A pre-publish collision guard and state cardinality gate were added. The frozen Stage 8 state engine itself was not modified.

### LinkedIn source-health key mismatch

Shadow run `33918314776` passed state identity and replay, but reporting showed one UNKNOWN source-health entry because LinkedIn records used `linkedin_mads` while Stage 10 diagnostics used `linkedin`.

Resolution: diagnostics now use `linkedin_mads`, a regression locks the mapping, and strict acceptance rejects any nonzero UNKNOWN source-health count.

## Regression and freeze gate

- Stage 10 tests: 13 PASS
- Stage 9 tests: 12 PASS
- Stage 8 tests: 29 PASS
- Stage 7 tests: 24 PASS
- Stage 6 tests: 21 PASS
- Stage 5 tests: 11 PASS
- Stage 4 tests: 4 PASS
- Total unittest methods: 114 PASS
- Stage 7 freeze verifier: PASS
- Stage 8 freeze verifier: PASS
- Stage 9 freeze verifier: PASS
- Stage 10 freeze verifier: PASS
- Stage 10 protected blobs: 13

## Scope boundary after acceptance

Stage 10 certifies the end-to-end pre-production path and strict live shadow behavior. It does **not** activate the production scheduler and does not certify the final V1.0 operational release. Those actions belong to the next explicitly approved stage, `V1.0_VALIDATED_OPERATIONAL_INTERNATIONAL_PIPELINE`.
