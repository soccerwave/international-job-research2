# Data and Policy Contract — V0.3

## Purpose

This contract defines the stable boundary between collection, deterministic policy routing, and the later scientific evaluator.

The system is recall-biased. Missing or ambiguous evidence must not silently become rejection evidence.

## Canonical vacancy contract

Every shard-enriched vacancy must conform to `schemas/vacancy.schema.json` with schema version `VACANCY_SCHEMA_V1.0.0`.

The record separates source identity and retrieval status, normalized position identity, location, dates and deadline semantics, contract and salary, Full JD/detail integrity, explicit requirement evidence, deterministic pre-evaluation classification, and provenance.

`source_record_id` is source-local and stable where possible. `canonical_id` is nullable in shard output and is assigned only after central cross-source canonicalization.

## Full JD contract

`description.detail_status` is authoritative for detail integrity:

- `FULL`
- `PARTIAL`
- `UNAVAILABLE`
- `FETCH_FAILED`
- `BLOCKED`
- `NOT_ATTEMPTED`

A failed or unavailable Full JD must never be treated as evidence that a job is irrelevant or closed.

## Pre-evaluation dispositions

Only four values exist before Stage 7:

- `ELIGIBLE_FOR_EVALUATION`
- `NEEDS_DETAIL_REVIEW`
- `POLICY_REVIEW`
- `POLICY_SKIP`

`POLICY_SKIP` requires explicit evidence matching a configured hard blocker.

`NEEDS_DETAIL_REVIEW` is preferred when the evidence needed to make a safe decision was not retrieved.

`POLICY_REVIEW` is used for genuine ambiguity in title, level, domain, language, mobility, or methods.

## Separation of concerns

Collectors may parse explicit facts but do not decide scientific fit.

The Stage 3 policy layer may enforce deterministic scope rules and hard blockers but does not score fit.

The Stage 7 evaluator will own scientific fit, level fit, methods fit, language, mobility, registration, contract suitability, and overall recommendation.

The central finalizer owns cross-source de-duplication, provenance aggregation, evaluation integration, availability and state.

## Unknown values

Unknown salary, contract duration, sponsorship, language, method expectations, or missing Full JD are not negative evidence by themselves.

Use nulls and explicit status fields. Do not invent defaults.

## Evidence requirement

Hard blockers require explicit posting evidence. A title-only guess is insufficient except for deterministic role categories such as a clearly identified PhD-student role or French MCF faculty title.

Preferred or desirable criteria do not create hard blockers.

## Market policy

Market scope is defined only in `config/markets.json`.

Core markets receive dedicated plus shared-source coverage.

Opportunistic markets receive shared-source coverage only.

Excluded markets do not receive dedicated queries in the initial pipeline.

## Role policy

Role normalization and country-specific aliases are defined in `config/roles.json`.

Primary role families are searched and evaluated first. Secondary research-scientist and project-management families remain disabled by default until intentionally enabled.

## Scientific profile

The declared profile in `config/scientific_profile.json` is evidence-bounded.

The `do_not_infer` list is as important as the capability list. Exposure to MRI does not imply advanced independent fMRI processing; neuroscience does not imply electrophysiology or optogenetics; data analysis does not imply advanced ML; exercise physiology does not imply clinical licensure.

## Mobility

Mobility is a separate dimension from scientific fit.

Country defaults in `config/mobility_policy.json` are routing aids, not legal conclusions. Time-sensitive immigration details must be re-verified before a final mobility rejection.

## Language

Country is not language evidence. Only explicit posting language requirements are evaluated.

The main deterministic language blocker currently frozen is explicit German C1/C2 required for teaching. Other unconfirmed mandatory local-language requirements normally route to review.

## Change control

Changes to schema fields or enums, market tier or country scope, primary/secondary role-family policy, local title mapping, declared scientific profile or do-not-infer constraints, mobility routing, language routing, blocker definitions, or fail-open precedence require a version bump and changelog entry.
