# Luna-led reporting transition (stages 1 and 2)

Status: candidate implementation on isolated branch; no Production authority or R2 publication changes.

## Decision contract
- Existing Rule classifier and dual-path routing continue to create the MAIN and Rescue candidate populations.
- Rule recommendation remains independent and stored for audit, not used to order the user-facing results.
- Existing frozen Luna model, profile, prompt, triage and Full evaluator are unchanged.
- Rescue candidates are promoted **only in the report** when their Full Luna decision is STRONG_APPLY, APPLY or REVIEW.
- Initial source provenance is immutable in the report: Source Path = MAIN or RESCUE. MAIN wins an overlap.
- Final MAIN sheet is sorted by Luna decision: STRONG_APPLY > APPLY > REVIEW.
- Luna SKIP goes to SKIPPED, not silently destroyed. MAIN with unavailable/failed Luna goes to NO_LLM_RESULT, not silently destroyed.
- Rule/Luna disagreements for original MAIN remain visible in DISAGREEMENTS and experiment evidence.
- No canonical state, routing, R2 evidence, cache, or existing Shadow report is changed.

## Outputs
The existing `llm_shadow_report.xlsx` remains unchanged. The shadow runner additionally emits `luna_led_report.xlsx` with:
1. MAIN: Luna-positive original MAIN plus favorable Rescue Full results.
2. SKIPPED: Luna SKIP across both paths.
3. NO_LLM_RESULT: original MAIN lacking a valid Luna decision.
4. DISAGREEMENTS: post-hoc Rule vs Luna disagreements from original MAIN.

All visible rows include Source Path where relevant.

## Later work deliberately excluded
- Do **not** switch the authoritative production/Telegram/R2 latest report pointer yet.
- Do **not** add Alignerr exclusions here (separate stage 3).
- Before publication, test real run artifacts, verify publisher compatibility, and explicitly choose cutover behavior (stage 4).
