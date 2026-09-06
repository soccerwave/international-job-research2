# ADR-002 — Central Finalizer Is the Only Canonical State Writer

**Status:** Accepted

**Date:** 2026-09-04

## Context

Independent collection shards may run concurrently. If each shard updates NEW/SEEN state directly, duplicate identities, ordering differences, retries, and overlapping production runs can corrupt history.

## Decision

Only the central finalizer may mutate canonical vacancy state.

Collection shards may emit immutable observations and may use temporary transport caches, but they do not write global NEW/SEEN/changed/reopened state.

## Required semantics

- A failed or missing shard is not evidence that a vacancy closed.
- A partial source run cannot expire previously observed jobs merely because they were absent from that partial output.
- State mutation occurs only after successful canonical finalization.
- Overlapping finalizers must be serialized or otherwise protected against concurrent canonical writes.

## Consequences

- State semantics are easier to reason about and test.
- Collection retries are safe.
- The finalizer becomes a critical component and therefore requires strict validation and atomic publication in Stage 8.
