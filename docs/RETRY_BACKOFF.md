# Phase 1 Stage 4.11: Retry/backoff semantics

## Scope

This stage repairs the shared HTTP retry contract only. It does not change pagination, query taxonomy, source coverage, evaluator/scoring, Full-JD semantics, date normalization, or source selection.

## Previous contract

The shared collector session retried only GET requests for 429/500/502/503/504 and explicitly ignored `Retry-After`. This meant idempotent discovery POST requests such as Workday listing APIs and CoreHR search forms had no transport retry protection, while server-directed cooldowns on ordinary GETs were also ignored.

## New contract

`make_session()` now applies one bounded policy to collector read/search traffic:

- retry budget: 2 by default for total/connect/read/status failures;
- exponential fallback backoff factor: 0.6 by default;
- retryable statuses: 429, 500, 502, 503, 504;
- retryable methods: GET and POST;
- `Retry-After` is respected when supplied by the server;
- non-retryable statuses such as 400 are returned without retry.

POST is included because POST operations under `src/sources` are discovery/search operations, not application submission or other state-changing actions. The Stage 4.11 CI gate inventories `.post(` call sites and fails if a new source file introduces POST without explicit review.

EURAXESS retains its source-specific retry implementation from Stage 4.1; that collector intentionally remounts/handles transport behavior locally and is not reworked here.

## Focused validation

The focused tests run a local HTTP server and prove behavior rather than only inspecting configuration:

1. GET receives 503 then succeeds and is retried exactly once.
2. POST receives 429 plus `Retry-After: 0`, then succeeds and is retried exactly once.
3. POST 400 is not retried.
4. GET and POST are the only shared allowed methods.
5. retry counts and backoff remain bounded.

## Live wiring validation

A bounded live gate executes one Workday USyd record and one CoreHR UCD record using the production collectors, verifying that the shared session change does not break the two POST-backed discovery paths. The live check does not claim that either external service emitted a 429/5xx during the probe; retry behavior itself is established deterministically by the local transport regressions.

Full production reliability certification remains pending for the later certification stage.
