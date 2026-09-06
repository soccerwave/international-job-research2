# Finalizer Fan-in Contract V1.0.0

Version: `FINALIZER_FANIN_CONTRACT_V1.0.0`

## Responsibilities in Stage 4

The finalizer:

1. discovers shard manifests for one run id;
2. verifies each bundle and its checksums;
3. rejects `ERROR`, corrupt, or mismatched bundles without aborting healthy inputs;
4. concatenates accepted vacancy records;
5. writes an immutable `records.json` and `summary.json` for that finalizer run.

## Explicit non-responsibilities in Stage 4

The finalizer does not yet:

- canonicalize identities across sources;
- cross-source deduplicate;
- score scientific fit;
- decide mobility or language;
- write NEW/SEEN state;
- persist to R2;
- build Excel or Telegram outputs.

Those remain assigned to later roadmap stages.

## Single-writer invariant

Stage 4 establishes the code boundary that later becomes the only canonical state writer. No shard receives a state-store interface.
