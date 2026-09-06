# Shard Artifact Contract V1.0.0

Version: `SHARD_ARTIFACT_CONTRACT_V1.0.0`

## Purpose

Each collection shard is an independent producer. It may discover vacancies, fetch source-specific detail pages, and emit Stage 3 vacancy records, but it must never read or write canonical shared state.

## Directory contract

```text
artifacts/<run_id>/shards/<shard_id>/
├── records.json
├── diagnostics.json
└── manifest.json
```

All three files are immutable for a given `<run_id>/<shard_id>` pair. A retry must use a new run id or an explicitly versioned attempt id; silent overwrite is forbidden.

## Manifest

The manifest contains:

- contract version
- run id
- shard id
- source ids
- shard status: `OK`, `PARTIAL`, or `ERROR`
- record count
- relative record/diagnostic paths
- SHA-256 checksums
- producer version
- immutable flag

The finalizer must verify checksums before accepting a shard.

## Failure semantics

- A collector exception is contained by the shard boundary and produces an `ERROR` diagnostic plus an immutable manifest.
- A failed shard does not imply that previously known vacancies from that shard are closed.
- The finalizer may continue with healthy shards and return `PARTIAL`.
- Missing shards are not interpreted as empty sources.

## Stage boundary

Stage 4 does not implement scientific fit, mobility decisions, cross-source dedupe, NEW/SEEN state, R2 publication, Telegram, or Excel reporting.
