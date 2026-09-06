# ADR-001 — Independent Collection Shards with a Central Finalizer

**Status:** Accepted

**Date:** 2026-09-04

## Context

The Spain production bot runs many sources through one production search job. Per-source failures are handled independently, but expanding to multiple countries and large ATS families would increase runtime coupling and create a larger failure domain.

## Decision

Use one codebase with independently runnable collection shards and one central finalizer.

A collection shard owns network/source behavior. The finalizer owns cross-source behavior.

### Shard responsibilities

- discovery;
- pagination;
- completeness diagnostics;
- source-local de-duplication;
- Full JD retrieval where feasible;
- source-local normalization;
- immutable output + manifest.

### Finalizer responsibilities

- validate shard manifests;
- merge shard outputs;
- canonicalize;
- cross-source de-duplicate;
- merge provenance;
- evaluate;
- update canonical state;
- publish reports and archives.

## Rejected alternative

A single mega-run containing every international source was rejected because it reproduces the scaling weakness of the Spain orchestration at a much larger source count.

A separate repository per country was also rejected because it would fragment evaluator/state/reporting logic and create avoidable duplication.

## Consequences

- Sources can fail and rerun independently.
- Expensive ATS families can be isolated.
- Finalization remains deterministic and centralized.
- Stage 4 must define shard-output contracts and fan-in orchestration.
