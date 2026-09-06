# ADR-000 — Separate International Repository and Donor-First Policy

**Status:** Accepted

**Date:** 2026-09-04

## Context

The Spain production bot is a validated operational system with Spain-specific source registry, production history, state semantics, and a frozen Spain-calibrated evaluator. The international project changes both market scope and execution topology.

At the same time, significant reusable engineering exists in:

- `soccerwave/researcher-job-search`;
- `MadsLorentzen/ai-job-search`;
- regional derivatives of Mads.

## Decision

The international system will live in a separate repository rather than turning the Spain production repository into a multi-country system.

Reuse will be selective. Every candidate component is classified as one of:

- `COPY_AS_IS`
- `ADAPT`
- `REWRITE`
- `DO_NOT_REUSE`
- `REFERENCE_PATTERN_ONLY`

Before writing a new collector or ATS adapter from scratch, engineers must inspect the donor hierarchy documented in `DONOR_COMPONENT_REGISTRY.md`.

External donor code may be reused only after:

1. pinning the origin commit;
2. identifying the origin path;
3. checking the applicable license;
4. live-validating behavior against the current portal;
5. recording local modifications.

## Consequences

### Positive

- Spain production stability is protected.
- International architecture can evolve independently.
- Existing validated work is not discarded.
- Duplicate implementation effort is reduced.
- Third-party provenance remains auditable.

### Negative

- Some utilities may initially exist in two repositories.
- Future upstream fixes may need explicit cherry-pick/adaptation rather than appearing automatically.
- Donor tracking adds documentation overhead.
