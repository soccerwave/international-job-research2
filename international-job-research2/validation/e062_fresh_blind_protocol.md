# E0.6.2 Fresh Blind Validation Protocol

Status: LABELS_LOCKED_BEFORE_SCORING
Candidate: E0.6.2_CONTEXT_LOCALIZATION_CANDIDATE
Frozen evaluator blob: 703327844b12a7e885da1ddf477e4feb22c87db3
Source production run: 33968147221
Source artifact: 9970107756
Source artifact digest: sha256:c7c5836214b5de1105631a6ed4445a5884763f4d6e1447360669508578dd34b0
Source main commit: 46da6c807f555ab81a4a3fc8b4986bd49db011c1

## Why this run is valid

The production inventory was collected after the exact E0.6.2 freeze was merged to main. The evaluator candidate was not used by production and no E0.6.2 predictions were inspected while selecting or labeling the validation sample.

## Sample construction

The locked sample has 80 unique canonical vacancies:

- 64 records selected deterministically with role/title-stratum and source diversification.
- 16 additional records selected deterministically from a profile-anchor pool to ensure the validation has enough recall pressure and is not dominated by obvious unrelated jobs.
- The two non-FULL detail records in the inventory are represented.
- Selection used structural fields, source, title text, and profile-anchor text only. It did not use E0.6.2 outputs.

## Labeling boundary

Reference labels were assigned from the raw vacancy title, raw/full vacancy text, structural metadata, stored candidate profile, and the project policy. E0.6.2 predictions were not consulted.

The labeling policy remains recall-first/fail-open:

- material ambiguity may be REVIEW;
- missing detail alone is not SKIP;
- clear role-stage, domain, professional, method, or eligibility evidence may justify SKIP;
- NEEDS_DETAIL_REVIEW is recorded separately from scientific REVIEW.

The two records marked needs_detail_review are plausible enough that missing essential detail should keep them visible for manual review.

## Promotion gate locked before scoring

- exact recommendation accuracy >= 0.90
- surfaced precision >= 0.90
- surfaced recall >= 0.75
- critical false negatives = 0

Surfaced = STRONG_APPLY, APPLY, or REVIEW.

Any E0.6.2 behavior change after this lock invalidates this validation and starts a new candidate cycle. If the one-shot score fails, this sample becomes burned development evidence and cannot be reused as promotion evidence.
