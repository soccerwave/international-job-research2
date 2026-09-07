# Phase 1 Stage 4.10: Date normalization

## Scope

This stage fixes centralized date normalization only. It does not change pagination, retry/backoff, query taxonomy, Full-JD semantics, evaluator/scoring, source selection, or board-coverage logic.

## Canonical contract

`src/sources/shared/common.py::day_iso()` is the canonical date normalizer used by `make_record()` for `posted_at` and `deadline_at`.

Supported evidence includes:

- ISO calendar dates and ISO/RFC3339 timestamps, including `Z` and numeric offsets.
- Common European academic-job formats such as `14/09/2026`, `14.09.2026`, `14-09-2026`, `14 September 2026`, and `14 Sep 2026`.
- Unambiguous named-month formats such as `August 17, 2026`.
- Ordinal suffixes and benign source labels such as `Closing date: 14th September 2026`.
- Workday-style relative posting dates including `Posted Today`, `Posted Yesterday`, `Posted 5 Days Ago`, and `30+ Days Ago`.

Unknown or non-date text remains `None`; the normalizer does not invent a date.

## Relative-date semantics

Relative dates are resolved against the same `collected_at` reference used by the record. This prevents different calls in one record from drifting across a date boundary.

## ISO offset semantics

The schema models a calendar day, not a timestamp instant. Therefore an ISO timestamp such as `2026-09-01T00:30:00+02:00` normalizes to `2026-09-01T00:00:00+00:00`; it is not converted to UTC first and shifted to the previous day.

## Numeric ambiguity

Slash-separated numeric dates are interpreted day-first, consistent with the repository's Europe/UK-oriented source scope. The stage does not add US month-first numeric guessing.

## Validation

Ten focused regression tests cover legacy formats, ISO timestamps, timezone offsets, named-month dates, ordinal labels, relative dates, unknown text, and one-reference `make_record()` behavior.

A bounded live gate validated real date output from:

- Workday Sydney
- SmartRecruiters Western Sydney University

Live validation run: `34046480940`.

Observed normalized posting date in both bounded samples: `2026-09-04T00:00:00+00:00`.

Artifact: `stage4-10-date-normalization`, artifact ID `9993250985`, digest `sha256:c206d5d4ad6f13105243c5afa7b2a618f5e49ba3e5400940d4db72b728c9f92d`.

Full all-source date-population certification remains a later certification step.
