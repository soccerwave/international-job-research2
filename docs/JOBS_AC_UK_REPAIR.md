# Phase 1 Stage 4.6: jobs.ac.uk metadata repair

## Scope

This stage repairs jobs.ac.uk metadata correctness only. It does not change production query taxonomy, pagination policy, country scope, evaluator logic, scoring, or source expansion.

## Stage 3 defects addressed

The frozen baseline contained 845 jobs.ac.uk records. Stage 3 found that the old `Location` regex could consume large portions of the job description when labels/layout changed: 35 location strings exceeded 80 characters, 26 exceeded 500, 23 exceeded 1,000, and the maximum exceeded 10,000 characters. It also defaulted every non-Ireland non-empty location to `GB`, creating obvious false country assignments for foreign jobs. Posted dates normalized for 0/845 records and deadlines for only 2/845.

## Repair

1. Metadata extraction is bounded by known jobs.ac.uk header labels instead of a free-running regex over the complete JD.
2. JSON-LD `JobPosting` is used first for hiring organization and structured country/location evidence when available.
3. Ordinal dates such as `17th August 2026` are converted to `17 August 2026` before the existing date normalizer.
4. Listing metadata is retained as a fallback for location, placed date, and deadline.
5. The dangerous rule `non-Ireland location => GB` is removed. Country codes are assigned only from explicit structured or textual country evidence; otherwise they remain unknown.
6. Foreign country evidence therefore remains foreign rather than being silently relabelled as United Kingdom.

## Safety boundary

This stage intentionally does not expand the jobs.ac.uk production query matrix. Query-taxonomy recall remains a later independent repair. It also does not change the global Full-JD status heuristic; that is a separate Stage 4 item.

## Validation boundary

Focused regressions verify bounded location extraction, foreign-country preservation, unknown-location fail-open behavior, and date normalization. A live current UK job-detail probe verifies structured country/date extraction, and a bounded live `research fellow` production sample checks that no oversized location strings remain and normalized dates reach canonical records.
