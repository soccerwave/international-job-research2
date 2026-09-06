# Public-readiness and GitHub Actions hardening

## Scope

This hardening prepares the repository to be made public without intentionally publishing production job-state/report data through GitHub Actions artifacts. It also reduces unnecessary Actions fan-out caused by release-freeze bookkeeping.

It does not make the repository public automatically and it does not rotate or create account secrets.

## Current-tree data policy

The tracked repository must not contain runtime exports or local secrets. `.gitignore` excludes `.env`, `.env.*` except `.env.example`, key material, runtime/output/artifact directories, CSV and Excel exports.

A public-readiness scanner rejects tracked `.env`, CSV/Excel, private-key/container formats and common literal secret signatures. The history mode scans unique Git blobs across fetched repository history and reports only the finding type, commit/ref and path; it does not print the matched secret value.

## Production Actions artifact privacy

Production matrix shards still need a transport between independent shard jobs and the authoritative finalizer. Moving this transport to a different backend is intentionally outside this small hardening change.

Instead, data-bearing Actions artifacts are now encrypted before upload using OpenSSL AES-256-CBC with PBKDF2 and a repository secret named `ARTIFACT_ENCRYPTION_KEY`.

The encrypted shard archive contains the immutable shard bundle and, when present, LinkedIn diagnostics for that shard. The finalizer downloads only encrypted archives and decrypts them in-memory/on-runner before finalization.

Final production evidence, including canonical records and Excel output, is likewise packed and encrypted before the temporary GitHub artifact is uploaded. Artifact retention is reduced from 30 days to 2 days.

The control-plane publisher downloads the encrypted production artifact and decrypts it with the same repository secret. It no longer uploads a second GitHub artifact containing the clean Excel preview/report. The user-facing report remains published to the private R2 destination and delivered through the existing Telegram path.

If `ARTIFACT_ENCRYPTION_KEY` is absent, production and publishing fail closed before raw data is uploaded.

## Actions-minute optimization

Release-freeze synchronization is bookkeeping and must not independently trigger historical live probes. `RELEASE_FREEZE_V1.1.0.json` was therefore removed from the automatic path triggers for Stage 4.9, 4.10, 4.11, 4.12, 4.13, 4.14 and Stage 5.1 workflows.

The V1 freeze verifier remains authoritative for manifest/hash integrity. The focused workflows still run when their implementation, tests, workflow, or evidence document changes.

The control-plane publisher no longer runs automatically on ordinary pushes to evaluator/reporting files. It runs after a successful production workflow or by explicit `workflow_dispatch`. This avoids rebuilding and republishing against a stale production artifact after unrelated code changes.

## Required setup before making the repository public

1. Create a high-entropy repository Actions secret named `ARTIFACT_ENCRYPTION_KEY`. Use a randomly generated value of at least 32 bytes. Do not reuse the R2 or Telegram credentials.
2. Delete historical data-bearing GitHub Actions artifacts/runs that were created before artifact encryption. The connected automation interface used for this hardening can list/download artifacts but cannot delete them, so this cleanup must be performed in GitHub's Actions UI or with an account token/API that has Actions write permission.
3. Run `Public Readiness Security Gate` once with full history available. It executes `python scripts/check_public_readiness.py --history` and an encryption round-trip test.
4. Confirm the production workflow and control-plane publisher succeed once with the encryption secret configured before relying on the public repository for scheduled production.
5. Only then change repository visibility to public.

## Historical artifact cleanup

At minimum, delete old runs/artifacts for:

- `International Academic Job Search Production`, because previous runs uploaded raw shard bundles, LinkedIn diagnostics and final production evidence.
- `Publish International Control Plane Report`, because previous runs uploaded the clean Excel/report preview artifact.

Focused Stage 4/5 diagnostic artifacts contain public vacancy-source diagnostics rather than authoritative user state, but they may also be deleted if a clean public Actions history is preferred.

## Certification boundary

This hardening establishes a safer future artifact policy and a repository/history scanner. It cannot itself delete already-retained Actions artifacts through the currently connected GitHub interface, and it does not prove that GitHub has removed every historical log or artifact until the historical cleanup and full-history security gate have been completed.
