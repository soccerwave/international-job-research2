# Evaluator E0.8 fresh-blind result and roadmap closure

## Decision

E0.8 is **not promoted**. The final fresh post-freeze blind gate failed under the predeclared thresholds. The current evaluator-improvement roadmap is therefore **closed without E0.9**, exactly as locked before scoring.

The final sealed holdout remains unopened and must not be used to tune this rejected candidate.

## Blind evidence

- Frozen candidate: `E0.8_ROUTING_GENERALIZATION_CANDIDATE`
- Candidate blob: `3086abcbd5d4c941e2c0f6bafb73cb9724bf3902`
- Freeze merged to `main`: `b327c1754e8f3176c3149c6d7d375176c53e253f`
- Fresh production run: `33973966435`
- Production artifact: `9971777879`
- Production artifact digest: `sha256:a79249f46c8291b2c5c9b2d00b27a6b2efaafc65224eb98cbe24086c246f6314`
- Selection lock commit: `e4a855b90a569e9b8eb33575d0c67a5a69996484`
- Human label lock commit: `469dcd6328aedf222e5e2bb225f14062e46bfa76`
- One-shot scoring workflow: `33975048981`
- Score artifact: `9972058741`
- Score artifact digest: `sha256:a2013d0ec9cd0e7b2f953d7d142e43a62624f7130fb12cd32ed8892198300b62`

Selection and labels were locked before E0.8 predictions were computed. Non-new strata excluded the burned E0.7 blind set.

## Result

| Metric | Result | Gate | Outcome |
| --- | ---: | ---: | --- |
| Route accuracy | 97.5% | >= 90% | PASS |
| Operational surfaced precision | 75% | >= 90% | **FAIL** |
| Operational surfaced recall | 75% | >= 75% | PASS |
| Critical operational false negatives | 1 | 0 | **FAIL** |
| Detail-review false negatives | 0 | 0 | PASS |

Confusion: `HIDDEN->HIDDEN 75`, `HIDDEN->JOBS 1`, `JOBS->HIDDEN 1`, `JOBS->JOBS 2`, `NEEDS_DETAIL_REVIEW->NEEDS_DETAIL_REVIEW 1`.

The critical false negative was the `Fellowship position in Quality of Life 2026-2028`, labeled `JOBS/REVIEW` before scoring and predicted `HIDDEN/SKIP`. The principal junk leak was `Lecturer in Criminology`, labeled `HIDDEN` and predicted `JOBS/REVIEW`.

## Stop-policy enforcement

No rule adjustment is permitted inside this roadmap after this result. In particular:

- do not create E0.9;
- do not relabel or rescore this blind set to rescue E0.8;
- do not open the final holdout;
- do not wire E0.8 into production or user-facing reporting;
- preserve the accepted V1 runtime and current user-facing evaluator until a separate architecture/product decision is made.

The `NEEDS_DETAIL_REVIEW` second-sheet requirement remains important, but its production integration is deferred until the post-roadmap architecture/product decision establishes which evaluator/routing layer will own it.
