# LLM Shadow Report in R2

After every successful GPT-6 Luna shadow run, the human-review workbook is published to R2 in a dedicated namespace.

## Stable latest pointer

`llm/reports/latest/manifest.json`

This manifest always points to the most recently published successful shadow report.

## Run-scoped files

Each run is stored separately:

- `llm/reports/runs/<github-run-id>-<attempt>/shadow_summary.json`
- `llm/reports/runs/<github-run-id>-<attempt>/llm_shadow_report.xlsx`

The Excel workbook contains the existing three sheets:

- MAIN
- LLM_RESCUED
- DISAGREEMENTS

The latest pointer is updated only after both the summary and Excel payload are written and size-verified in R2.

This publication is visibility only. It does not make the LLM authoritative and does not modify the Rule report.
