# Phase 1 Stage 4.12: CNRS prefilter repair

## Scope

This stage removes the CNRS role-keyword prefilter from the production collection path. It does not change global query taxonomy, evaluator/scoring, pagination, retry/backoff, date normalization, Full-JD semantics, or source coverage.

## Previous behavior

The legacy CNRS parser accepted a concrete offer link only when the anchor text or nearby listing context matched:

`post-?doc|postdoctor|chercheur`

That was a role decision inside collection. Any CNRS offer outside those words was silently dropped before downstream policy/evaluator logic could inspect it. Examples include research-engineer or other research-support titles that can require a doctorate or be scientifically relevant despite not containing the legacy terms.

## New behavior

Production now routes `cnrs_emploi` to a dedicated CNRS collector that:

- accepts every concrete CNRS detail URL matching `/Offres/<category>/<offer>/Default.aspx`;
- rejects search, unit-listing, external-domain, and non-detail links;
- performs no role-keyword relevance filtering;
- preserves the existing `cnrs_emploi` source key;
- preserves the legacy source-record ID derivation so historical identity/dedup behavior is not changed by this repair;
- leaves downstream relevance decisions for the later policy/evaluator layer.

The legacy `portals.collect_cnrs` implementation is retained for comparison and rollback reference, but it is no longer the production `cnrs_emploi` path.

## Why this is recall-safe

The project is explicitly recall-biased: false positives are cheaper than false negatives. CNRS is itself a research-employment portal, so collecting concrete offers broadly is preferable to deleting jobs based on a narrow title vocabulary before full job details are available.

## Validation

Focused regressions verify that:

1. an `Ingénieur de recherche` offer without `postdoc`, `postdoctor`, or `chercheur` is retained;
2. ordinary postdoctoral offers remain retained;
3. CNRS search/unit pages and external-domain lookalikes are excluded;
4. duplicate offer URLs are deduplicated while preserving the legacy source ID;
5. the production `germany-france-primary` shard routes `cnrs_emploi` to the recall-safe collector.

The live gate downloads the current CNRS search page, runs both the legacy and new parsers over the same HTML, records how many concrete offer rows the old keyword prefilter would have dropped, and executes a bounded five-record collection through the new collector.

Full uncapped CNRS board certification remains pending for the later board-completeness and recall-certification stages.
