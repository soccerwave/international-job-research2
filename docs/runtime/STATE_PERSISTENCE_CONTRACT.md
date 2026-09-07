# State Persistence Contract — V1.0.0

Stage: `V0.8_STATE_PERSISTENCE`

## Ownership

Only the central finalizer may mutate durable state. Collection shards produce immutable evidence and never read or write shared state.

The state engine requires writer role `CENTRAL_FINALIZER`; any other writer role is rejected.

## Durable state

Schema: `STATE_SCHEMA_V1.0.0` in `schemas/state.schema.json`.

Each durable job stores conservative identity aliases, first/last seen timestamps, times seen, explicit lifecycle status, the last trustworthy snapshot, last state event, and last material change reasons.

## State events

- `NEW`: no durable alias matched an existing state entry.
- `SEEN`: existing vacancy observed again without a material vacancy change.
- `MATERIALLY_CHANGED`: stable/enriched vacancy evidence changed materially.
- `REOPENED`: an entry previously supported by explicit `CLOSED` evidence is later supported by explicit `OPEN` evidence.

Full-JD recovery/degradation is tracked separately as `DETAIL_RESOLVED` / `DETAIL_UNRESOLVED` quality events.

## Fail-open rules

- Absence from a later run never means closed.
- A failed/missing shard never means closed.
- `UNKNOWN` or `ERROR` source status never becomes closed.
- Full-JD fetch degradation is not a vacancy change and does not overwrite the last trustworthy enriched snapshot.
- Reopening requires prior explicit closed evidence followed by explicit open evidence.
- Fuzzy cross-source identity merging is not performed by the state engine.
- If aliases unexpectedly point to multiple durable entries, the engine fails closed on the write operation and reports an identity conflict rather than silently merging histories.

## Local durability

Local state is written atomically through temporary-file plus `os.replace` semantics. Corrupt or unsupported state is rejected rather than silently reseeded.

## R2 durability and concurrency

Default authoritative object: `state/current/state.json`.

Every publish also creates an immutable generation backup under `state/backups/`.

The authoritative object uses optimistic concurrency:

- first creation: `If-None-Match: *`
- subsequent generation: `If-Match: <previous ETag>`

A stale writer receives a precondition failure and must not overwrite the newer state. The R2 object is read back after each authoritative write and its stored SHA-256 metadata/content are verified.

Cloudflare R2 access is via its S3-compatible API and environment-provided credentials only. No R2 credential is committed to the repository.

## Required runtime configuration

Secrets:

- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`

Variables:

- `R2_BUCKET`
- `R2_ENDPOINT` (optional when the standard account endpoint is valid; required for jurisdiction-specific endpoints)

Optional:

- `R2_STATE_PREFIX`

## Stage boundary

Stage 8 establishes state semantics, local atomic persistence, R2 compare-and-swap persistence, and the single-writer contract. Reporting, Telegram delivery, and production scheduling remain Stage 9+ work.
