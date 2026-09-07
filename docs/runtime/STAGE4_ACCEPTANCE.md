# Stage 4 Acceptance — V0.4_SHARDED_RUNTIME

Stage 4 passes when all of the following are true:

- independent shard execution exists;
- shard output is immutable per run/shard identity;
- shard manifest and diagnostics contracts exist;
- SHA-256 verification protects fan-in from corrupt/tampered bundles;
- one failed shard does not abort healthy shard fan-in;
- missing/failed shard is not interpreted as source closure;
- finalizer emits run summary and merged raw records;
- shard code has no canonical state writer;
- runtime tests exercise successful, failed, immutable, and fan-in paths;
- no production collector is introduced;
- no international evaluator is introduced;
- no R2/state/reporting implementation is introduced.
