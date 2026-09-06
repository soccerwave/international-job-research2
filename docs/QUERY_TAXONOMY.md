# Phase 1 Stage 4.14: Query taxonomy

## Scope

This stage changes only the role-search taxonomy used by LinkedIn Europe, LinkedIn Australia, and jobs.ac.uk. It does not change source coverage, evaluator/scoring, pagination, retry/backoff, date normalization, Full-JD semantics, or downstream role policy.

The project is recall-biased, but LinkedIn query expansion has a real runtime cost. Candidate queries were therefore tested against the pre-4.14 production baseline using a bounded first-page live diagnostic before any production query set was changed.

## Pre-4.14 baselines

LinkedIn Europe:

- `postdoctoral researcher`
- `research fellow`
- `assistant professor`
- `lecturer`

LinkedIn Australia:

- `postdoctoral researcher`
- `research fellow`
- `lecturer`

jobs.ac.uk:

- `postdoctoral`
- `research fellow`
- `lecturer`
- `exercise`
- `neuroscience`

## Diagnostic candidates

The live diagnostic compared:

- `research associate`
- `research scientist`
- `postdoctoral fellow`
- `researcher`
- `research assistant`

LinkedIn was sampled in Germany, Ireland, and Australia using the pinned Mads transport, the existing 14-day age policy, and ten results per query. jobs.ac.uk was sampled using the first 25-result page for each query.

## Evidence summary

LinkedIn marginal unique results versus the pre-4.14 baseline:

| Query | Germany | Ireland | Australia | Decision |
|---|---:|---:|---:|---|
| research associate | 6 | 6 | 8 | Add |
| research scientist | 7 | 8 | 10 | Do not add to LinkedIn: high commercial/AI/pharma noise and material runtime cost |
| postdoctoral fellow | 1 | 2 | 6 | Add |
| researcher | 10 | 8 | 10 | Do not add: broad high-noise taxonomy |
| research assistant | 7 | 10 | 10 | Do not add: broad and frequently junior/doctoral taxonomy |

The `postdoctoral fellow` samples included concrete missed postdoctoral titles, especially in Australia, including Postdoctoral Research Fellow, Postdoctoral Research Associate, and Postdoctoral Researcher variants. `research associate` also recovered concrete research-staff titles across all three sampled markets.

For jobs.ac.uk, the board itself is more academically constrained and query execution is cheaper than LinkedIn discovery. First-page marginal unique results were:

- `research associate`: 11
- `research scientist`: 16
- `postdoctoral fellow`: 18
- `researcher`: 13
- `research assistant`: 16

`researcher` and `research assistant` were still excluded because their sample contained substantial administrative, student, and unrelated-role noise. `research scientist` was retained for jobs.ac.uk because the host board is academic/research-focused and the query recovered additional research, postdoctoral, project-research, and fellowship results that were absent from the baseline first pages.

## Final production taxonomy

LinkedIn Europe:

- `postdoctoral researcher`
- `research fellow`
- `assistant professor`
- `lecturer`
- `research associate`
- `postdoctoral fellow`

LinkedIn Australia:

- `postdoctoral researcher`
- `research fellow`
- `lecturer`
- `research associate`
- `postdoctoral fellow`

jobs.ac.uk:

- `postdoctoral`
- `research fellow`
- `lecturer`
- `exercise`
- `neuroscience`
- `research associate`
- `postdoctoral fellow`
- `research scientist`

## Certification boundary

This stage certifies that the query expansion is evidence-based and correctly wired into production and shadow configurations. The diagnostic is a bounded first-page marginal-recall comparison, not a proof of complete search recall. Full end-to-end recall and board-completeness certification remain later phases.
