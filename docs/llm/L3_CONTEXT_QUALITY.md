# L3 — Context Quality Layer

Status: IMPLEMENTED ON L3 BRANCH

## Purpose

Improve vacancy context quality before independent LLM evaluation without converting the semantic evaluator into a keyword/rule system.

The L0 independence and Full-JD-first contracts remain unchanged.

## Processing order

`canonical Full JD -> conservative cleanup -> source-heading section extraction -> optional soft-budget truncation -> L0 input -> LLM`

## Conservative cleanup

The context layer removes only obvious interface boilerplate lines such as cookie controls, navigation links, print/share controls and isolated Apply/Save controls. It also removes exact repeated text blocks when the normalized block is long enough to avoid accidental deletion of short repeated requirements.

It does not paraphrase, summarize, classify or keyword-filter vacancy prose.

## Section preservation

The layer can recognize source headings for:

- responsibilities / duties;
- essential / required / minimum criteria;
- desirable / preferred criteria.

Extraction is heading-based. It does not decide that arbitrary sentences are mandatory or preferred from keyword matches.

If the collector already supplied an explicit source-derived section field, that field takes precedence over text extracted from the Full JD.

## Truncation policy

Normal vacancies are not truncated. The evaluator currently uses a soft ceiling of 120,000 cleaned characters.

If the cleaned Full JD exceeds the ceiling:

1. essential criteria are protected;
2. desirable criteria are protected;
3. responsibilities are protected;
4. remaining budget is split across the beginning and end of the source text.

No keyword-based summarization is used.

If the protected source sections alone exceed the soft ceiling, they are retained verbatim and the context is allowed to exceed the ceiling rather than silently dropping requirements.

## Telemetry

L3 adds context-quality metadata to shadow telemetry and stored shadow records:

- original characters;
- cleaned characters;
- final characters;
- obvious boilerplate lines removed;
- exact duplicate blocks removed;
- whether truncation occurred;
- truncation strategy.

This metadata is not exposed to the LLM as a rule-based fit signal.

## Authority boundary

L3 does not:

- change deterministic production recommendations;
- join rule-based output before LLM evaluation;
- implement L4 sampling;
- implement L5 rule/LLM comparison;
- promote or demote any production job;
- infer missing candidate capabilities.

## Acceptance criteria

L3 is acceptable when CI proves that:

1. obvious UI boilerplate can be removed without rewriting vacancy prose;
2. exact duplicate source blocks are removed conservatively;
3. responsibilities, essential criteria and desirable criteria are preserved from source headings;
4. no truncation occurs below the soft budget;
5. long contexts preserve requirement/responsibility sections before head/tail source text;
6. protected source sections are never silently cut merely to obey the soft budget;
7. L0 rule-evaluator independence remains intact.

Next roadmap stage after L3 is L4 sampling strategy.
