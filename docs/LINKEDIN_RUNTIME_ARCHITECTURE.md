# Phase 1 Stage 4.4: LinkedIn runtime architecture

## Scope

This stage changes LinkedIn Europe runtime topology only. It does not change query taxonomy, country coverage, job-age policy, pagination policy inside the collector, detail-enrichment policy, subprocess timeout, evaluator behavior, scoring, or source expansion.

Stage 4.2 made LinkedIn execution observable. Stage 4.3 preserved completed work. Stage 4.4 uses fresh runtime evidence to reduce serial wall-clock and failure blast radius without introducing concurrency inside the Mads collector.

## Fresh profiling evidence

Before changing production topology, a diagnostic-only GitHub Actions run profiled uncapped discovery with the pinned Mads transport and the exact four current Europe queries. Detail enrichment was disabled so discovery cost could be measured independently.

Profile run: `34042024861`
Artifact: `9991993739`

### Ireland

- 496 unique listings
- 74 search pages
- 31.18 seconds discovery
- 31.43 seconds total collector time
- 0 search failures
- postdoctoral researcher: 16 pages / 150 returned rows
- research fellow: 43 pages / 415 returned rows
- assistant professor: 5 pages / 33 returned rows
- lecturer: 10 pages / 84 returned rows

### Germany

- 1,297 unique listings
- 196 search pages
- 94.56 seconds discovery
- 95.17 seconds total collector time
- 0 search failures
- postdoctoral researcher: 67 pages / 660 returned rows
- research fellow: 33 pages / 320 returned rows
- assistant professor: 19 pages / 172 returned rows
- lecturer: 77 pages / 760 returned rows

The profile demonstrates that uncapped discovery itself is substantial and serial across country/query loops. Germany alone required roughly three times Ireland's discovery wall-clock. Keeping all twelve European countries inside one shard therefore makes country costs additive before considering detail enrichment.

## Runtime partition decision

The former single `linkedin-europe` shard is replaced by four independent GitHub matrix shards:

- `linkedin-europe-germany`: Germany
- `linkedin-europe-west`: Netherlands, Ireland, United Kingdom, Belgium
- `linkedin-europe-france-austria`: France, Austria
- `linkedin-europe-opportunistic`: Italy, Portugal, Czechia, Poland, Luxembourg

The union is exactly the same twelve countries with no overlap. Germany is isolated because fresh profiling identifies it as a heavy discovery workload.

Every partition retains the same logical source ID `linkedin_europe`, report key `linkedin_mads`, four production queries, 14-day job-age window, uncapped pagination, and detail enrichment. This is runtime decomposition, not source expansion.

## Why GitHub-level partitioning

Partitioning at the workflow matrix level allows independent runners to execute country groups concurrently and isolates cancellation/failure to a smaller group. It avoids adding threads or concurrent Mads subprocesses inside one runner, which would introduce a new rate-limit and transport-risk surface before it is justified.

Observability and durability from Stages 4.2 and 4.3 apply automatically because every new shard ID starts with `linkedin` and the production entrypoint creates a separate diagnostics/checkpoint directory for each shard.

## Certification boundary

Stage 4.4 validates runtime decomposition and bounded live execution of the partitions. It does not claim a measured end-to-end production speedup yet. Actual uncapped Europe-plus-detail wall-clock, source completeness, and recall remain subject to a fresh full production run and later certification stages.
