# Architecture Baseline

Version: `V0.2_ARCHITECTURE_BASELINE`

## 1. Purpose

Build a recall-biased international academic job-search pipeline that can scale across core markets without turning one source failure, one slow ATS, or one malformed vacancy into a failure of the entire search.

The pipeline must preserve ambiguity rather than silently discard it. Detail failures, unknown sponsorship, uncertain titles, and incomplete source metadata remain visible for later evaluation or human review.

## 2. Topology

```text
                           +------------------------+
                           | Trigger / coordinator  |
                           +-----------+------------+
                                       |
            +--------------------------+--------------------------+
            |                          |                          |
            v                          v                          v
   +----------------+         +----------------+         +----------------+
   | collection     |         | collection     |   ...   | collection     |
   | shard A        |         | shard B        |         | shard N        |
   +-------+--------+         +-------+--------+         +-------+--------+
           |                          |                          |
           +------------- immutable shard outputs -------------+
                                      |
                                      v
                           +------------------------+
                           | Central finalizer      |
                           +-----------+------------+
                                       |
                    +------------------+------------------+
                    |                  |                  |
                    v                  v                  v
                 State/R2          Reports           Telegram
```

## 3. Collection shard contract

A shard is an independently executable failure domain. It may contain one source or several sources only when their runtime and failure characteristics make grouping sensible.

A shard SHOULD:

1. discover vacancies;
2. paginate completely or declare why it could not;
3. fetch Full JD/detail at the source layer where feasible;
4. normalize source observations to the Stage 3 contract;
5. de-duplicate within the shard without destroying provenance;
6. emit immutable vacancy observations;
7. emit a manifest and source diagnostics;
8. fail softly for individual sources wherever possible.

A shard MUST NOT mutate canonical global state.

## 4. Central finalizer contract

The finalizer is the only component allowed to write canonical shared state.

It MUST:

1. validate shard manifests and version compatibility;
2. distinguish successful, partial, failed, and missing shard outputs;
3. merge observations from available shards;
4. canonicalize identities across sources;
5. preserve all source provenance;
6. evaluate fit and mobility only after canonicalization;
7. apply availability and NEW/SEEN/changed/reopened semantics;
8. publish state atomically;
9. generate durable canonical snapshots and downstream reports.

A missing or failed shard is never interpreted as proof that previously known jobs disappeared.

## 5. Full JD ownership

Full JD acquisition belongs in the source/shard layer by default because:

- detail URLs and identifiers are source-specific;
- attachment/PDF fallback is source-specific;
- authentication/rate limiting is source-specific;
- completeness diagnostics are more meaningful when search + detail are observed together.

The finalizer consumes whatever detail state the shard reports. Missing detail should remain explicit and route to review later rather than becoming an implicit rejection.

## 6. Runtime boundaries

### Python 3.12

Preferred for:

- canonical models and validation;
- finalizer;
- cross-source de-duplication;
- availability;
- evaluator;
- state engine;
- R2 transport;
- Excel and Telegram reporting;
- Python-native collectors.

### Bun/TypeScript

Allowed for portal CLI adapters when a validated donor exists or the Mads portal contract is advantageous.

The central system treats such adapters as external transports with explicit structured output and diagnostics.

## 7. Donor-first rule

Before greenfield source work:

1. inspect Spain production implementation;
2. inspect Mads upstream;
3. inspect relevant Mads-derived regional repositories;
4. inspect other credible implementations if needed;
5. only then implement from scratch.

Donor existence does not equal acceptance. Every adopted adapter must be live-validated against the current portal and recorded in the donor registry.

## 8. State ownership

Canonical state is centralized and single-writer.

Shard output is immutable observation data, not application state.

Later Stage 8 design must protect against overlapping finalizers and use atomic publish semantics.

## 9. Version boundaries

At minimum every production run will eventually record:

- `pipeline_version`
- `schema_version`
- `evaluator_version`
- `source_registry_version`
- state semantics version
- per-shard implementation/manifest version

A silent source-policy or evaluator change is not permitted.

## 10. What is deliberately not decided in Stage 2

Stage 2 does not freeze:

- the final vacancy schema;
- evaluator weights or recommendation thresholds;
- exact production shard grouping;
- R2 object paths;
- report columns;
- source-specific implementation details;
- scheduler cadence.

Those decisions require their respective later stages.
