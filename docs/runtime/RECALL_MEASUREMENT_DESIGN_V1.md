# Stage 7.1 Recall Measurement Design

Status: implementation candidate pending CI and freeze closure.

This step defines how recall will be measured. It does not construct the reference set, calculate recall, change sources, or modify collector behavior.

## Primary recall metric

`END_TO_END_VACANCY_RECALL`

Unit: unique vacancy.

Formula:

`matched unique eligible reference vacancies / unique eligible reference vacancies`

The same vacancy observed on multiple reference sources counts once in the primary denominator. Source-observation recall is reported separately for diagnostic attribution.

## Reference-set independence

The reference set must be acquired independently of pipeline output and independently of pipeline collector code. The reference-source roster must be frozen before any comparison with pipeline results.

Eligibility adjudication is completed before pipeline match status is added. This prevents the denominator from being influenced by what the pipeline happened to find.

Required reference provenance includes source, URL, observation timestamp, title, institution, country, posting/deadline fields when available, role-family status, eligibility status, and eligibility reason.

## Market scope

Primary aggregate: the eight current core markets:

`NL, DE, IE, GB, BE, FR, AU, AT`

Opportunistic markets are measured and reported separately:

`IT, PT, CZ, PL, LU`

Excluded markets are not included in the primary recall denominator.

## Role scope

The primary denominator uses the currently frozen primary role families:

`POSTDOC`, `RESEARCH_FELLOW_POSTDOC`, `ASSISTANT_PROFESSOR`, `LECTURER`, `RESEARCH_ASSISTANT_PROFESSOR`, `TENURE_TRACK`, `JUNIOR_PROFESSOR`.

Conditional titles must be adjudicated with the frozen role policy before denominator entry. Unknown or ambiguous roles may not be silently excluded.

Secondary role families remain outside the primary denominator unless the role policy is intentionally changed. They can be reported separately.

## Time design

Measurement is prospective over 14 consecutive calendar days. This covers two complete weekly cycles and aligns with the existing 14-day LinkedIn discovery horizon.

Primary cohort: vacancies newly posted during the measurement window.

Vacancies already open at the start of the window form a separate active-stock cohort. Vacancies with unknown posting date but first independently observed during the window are also reported separately.

A reference vacancy counts as captured when the production pipeline observes it within 48 hours of the independent reference observation, or before its deadline if the deadline occurs sooner.

## Matching boundary

Stage 7.1 defines the matching policy but does not implement matching. Stage 7.3 owns implementation.

Match priority:

1. exact normalized detail/apply URL
2. exact source job ID when comparable
3. deterministic title + institution + country composite
4. manual review for ambiguous candidates

Title alone is never sufficient for automatic matching.

## Miss-attribution taxonomy

Stage 7.1 defines the following categories for later false-negative analysis:

- `SOURCE_NOT_COVERED`
- `QUERY_DISCOVERY_MISS`
- `PAGINATION_OR_LISTING_DISCOVERY_MISS`
- `PARSER_OR_EXTRACTION_MISS`
- `PRE_EVALUATION_FILTER_MISS`
- `TRANSIENT_RUNTIME_FAILURE`
- `MATCHING_OR_DEDUPLICATION_ISSUE`
- `UNKNOWN_REQUIRES_REVIEW`

`UNKNOWN_REQUIRES_REVIEW` is permitted and must never be silently reclassified as success.

## Reporting

Recall must always be reported with its denominator N. Required breakdowns are country, reference source, role family, institution, and miss category.

When numerical recall is computed in Stage 7.4, exact binomial 95% confidence intervals will be reported.

Precision is not the primary objective of Stage 7.

## Stage boundary

No source addition or removal is authorized before Stage 8. Stage 7 measures the existing pipeline.

Run:

`python scripts/verify_stage7_1_recall_design.py`
