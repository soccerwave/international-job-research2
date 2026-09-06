# Repository Layout Baseline

The Stage 2 repository contains structure but deliberately postpones Stage 3 schemas and Stage 4 runtime code.

```text
international-academic-job-search/
├── README.md
├── VERSION.json
├── CHANGELOG.md
├── THIRD_PARTY_NOTICES.md
├── .gitignore
├── .github/
│   └── workflows/          # Stage 4+
├── config/                 # Stage 3+
├── docs/
│   ├── architecture/
│   └── coverage/
├── schemas/                # Stage 3+
├── src/                    # Stage 4+
└── tests/                  # Stage 3/4+
```

## Future source layout principle

Do not hard-code one directory per country unless implementation evidence requires it. Prefer reusable provider/ATS adapters plus configuration, with source-specific collectors only for boards that cannot share an adapter.

A possible later shape is:

```text
src/
├── core/
│   ├── canonicalize/
│   ├── dedupe/
│   ├── availability/
│   ├── finalizer/
│   ├── state/
│   └── reporting/
├── sources/
│   ├── shared/
│   ├── portals/
│   ├── ats/
│   └── direct/
└── transports/
    ├── python/
    └── bun/
```

The exact module names are not frozen until Stage 4.
