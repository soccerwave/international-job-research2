"""Luna-led *presentation* of the existing immutable dual-path evaluations.

No routing, evaluator, canonical job, or Rule decision is modified.
The legacy shadow workbook remains available for historical comparisons.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import xlsxwriter

from src.llm.full_evaluation_routing import FullEvaluationRecord, ORIGIN_LLM_RESCUE, ORIGIN_MAIN
from src.reporting.llm_shadow_excel import (
    MAIN_COLUMNS, DISAGREEMENT_COLUMNS, FAVORABLE_LLM_DECISIONS,
    _agreement, _base_row, _full_record_map, _job_id, _llm_fields,
    _rule_recommendation, _write_sheet,
)

SOURCE_COLUMNS = (
    ("source_path", "Source Path", 14),
    ("llm_evaluation", "Luna Decision", 20),
    ("rule_evaluation", "Rule Evaluation (Shadow)", 23),
    ("llm_confidence", "Luna Confidence", 18),
    ("llm_reason", "Luna Reason", 58),
    *tuple(c for c in MAIN_COLUMNS if c[0] not in {
        "llm_evaluation", "rule_evaluation", "llm_confidence", "llm_reason", "agreement"
    }),
)
SKIPPED_COLUMNS = SOURCE_COLUMNS
DISAGREEMENT_SOURCE_COLUMNS = (("source_path", "Source Path", 14), *DISAGREEMENT_COLUMNS)
DECISION_ORDER = {"STRONG_APPLY": 0, "APPLY": 1, "REVIEW": 2}


def build_luna_led_rows(
    canonical_jobs: Iterable[dict[str, Any]],
    *,
    main_job_ids: Iterable[str],
    full_evaluation_records: Iterable[FullEvaluationRecord],
) -> dict[str, tuple[dict[str, Any], ...]]:
    jobs = {_job_id(j): j for j in canonical_jobs if _job_id(j)}
    main_ids = {str(i).strip() for i in main_job_ids if str(i).strip()}
    evaluations = _full_record_map(full_evaluation_records)
    main, skipped, pending, disagreements = [], [], [], []

    def add(job_id: str, origin: str) -> None:
        job = jobs.get(job_id)
        if job is None:
            return
        llm = _llm_fields(evaluations.get((job_id, origin)))
        decision = llm["llm_evaluation"]
        rule = _rule_recommendation(job)
        row = {
            **_base_row(job), **llm,
            "source_path": "MAIN" if origin == ORIGIN_MAIN else "RESCUE",
            "rule_evaluation": rule,
        }
        if decision in FAVORABLE_LLM_DECISIONS:
            main.append(row)
        elif decision == "SKIP":
            skipped.append(row)
        elif origin == ORIGIN_MAIN:
            pending.append(row)
        # Rescue records with missing/failed evaluations cannot be promoted:
        # they remain in the original routing/triage evidence, unchanged.

        if origin == ORIGIN_MAIN:
            agreement = _agreement(rule, decision)
            if agreement in {"MAJOR_DISAGREEMENT", "MINOR_DISAGREEMENT"}:
                disagreements.append({**row, "agreement": agreement, "severity": agreement})

    for job_id in sorted(main_ids):
        add(job_id, ORIGIN_MAIN)
    # MAIN wins on overlap, even if malformed upstream evaluations contain both origins.
    for job_id, origin in sorted(evaluations):
        if origin == ORIGIN_LLM_RESCUE and job_id not in main_ids:
            add(job_id, origin)

    secondary = lambda r: (str(r.get("country", "")).casefold(), str(r.get("title", "")).casefold(), r["source_path"])
    main.sort(key=lambda r: (DECISION_ORDER[r["llm_evaluation"]], *secondary(r)))
    skipped.sort(key=secondary)
    pending.sort(key=secondary)
    disagreements.sort(key=lambda r: (r["severity"] != "MAJOR_DISAGREEMENT", *secondary(r)))
    return {
        "MAIN": tuple(main),
        "SKIPPED": tuple(skipped),
        "NO_LLM_RESULT": tuple(pending),
        "DISAGREEMENTS": tuple(disagreements),
    }


def build_luna_led_xlsx(
    canonical_jobs: Iterable[dict[str, Any]],
    output_path: Path,
    *,
    main_job_ids: Iterable[str],
    full_evaluation_records: Iterable[FullEvaluationRecord],
) -> Path:
    rows = build_luna_led_rows(
        canonical_jobs,
        main_job_ids=main_job_ids,
        full_evaluation_records=full_evaluation_records,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(output_path)
    workbook.set_properties({
        "title": "International Academic Job Search — Luna-led Report",
        "subject": "Luna-authoritative ranking, immutable source provenance",
        "comments": "Report-only union of MAIN and favorable Rescue; Rule decisions remain shadow evidence.",
    })
    for name, columns in (
        ("MAIN", SOURCE_COLUMNS),
        ("SKIPPED", SKIPPED_COLUMNS),
        ("NO_LLM_RESULT", SOURCE_COLUMNS),
        ("DISAGREEMENTS", DISAGREEMENT_SOURCE_COLUMNS),
    ):
        _write_sheet(workbook, name=name, rows=rows[name], columns=columns)
    workbook.close()
    return output_path
