# ADR-003 — Hybrid Python and Bun/TypeScript Runtime

**Status:** Accepted

**Date:** 2026-09-04

## Context

The Spain production system is Python-centric but already installs Bun to use the Mads LinkedIn CLI. The Mads ecosystem provides a mature portal-skill contract and several useful TypeScript implementations.

Rewriting a validated donor CLI into Python solely for language uniformity would add risk without necessarily improving operations.

## Decision

Use Python 3.12 for the central orchestration/finalization/state/reporting core and Python-native collectors.

Permit Bun/TypeScript portal adapters where:

- the implementation comes from or closely follows a validated Mads portal pattern;
- preserving the donor transport is lower risk than rewriting it;
- the adapter honors the common vacancy/shard contract;
- CI can typecheck and test it independently.

Cross-runtime communication must use explicit file/JSON/CLI contracts rather than importing TypeScript into Python internals.

## Consequences

- Proven Mads adapters can be reused with less translation risk.
- CI and production environments need both Python and Bun.
- Stage 4 must define a stable adapter invocation contract and error semantics across runtimes.
