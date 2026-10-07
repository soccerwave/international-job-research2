from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import xlsxwriter

from src.evaluation.calibrated_e021 import with_calibrated_evaluation
from src.llm.full_evaluation_routing import FullEvaluationRecord, ORIGIN_LLM_RESCUE, ORIGIN_MAIN
from src.reporting.report import record_to_row

REPORT_VERSION = "LLM_SHADOW_REPORT_V0.1"
FAVORABLE_LLM_DECISIONS = {"STRONG_APPLY", "APPLY", "REVIEW"}

RULE_RANK = {
    "SKIP": 0,
    "LOW_PRIORITY": 1,
    "REVIEW": 2,
    "APPLY": 3,
    "STRONG_APPLY": 4,
}
LLM_RANK = {
    "SKIP": 0,
    "REVIEW": 2,
    "APPLY": 3,
    "STRONG_APPLY": 4,
}

MAIN_COLUMNS = (
    ("seen_status", "Change", 20),
    ("rule_evaluation", "Rule Evaluation", 20),
    ("llm_evaluation", "LLM Evaluation", 20),
    ("agreement", "Agreement", 24),
    ("llm_confidence", "LLM Confidence", 16),
    ("llm_reason", "LLM Reason", 58),
    ("title", "Title", 48),
    ("country", "Country", 18),
    ("role_family", "Role", 24),
    ("institution", "Institution", 36),
    ("city", "City", 20),
    ("deadline", "Deadline", 15),
    ("url", "Link", 12),
)

RESCUED_COLUMNS = (
    ("rule_evaluation", "Rule Evaluation", 20),
    ("llm_evaluation", "LLM Evaluation", 20),
    ("llm_confidence", "LLM Confidence", 16),
    ("llm_reason", "LLM Reason", 58),
    ("title", "Title", 48),
    ("country", "Country", 18),
    ("role_family", "Role", 24),
    ("institution", "Institution", 36),
    ("city", "City", 20),
    ("deadline", "Deadline", 15),
    ("url", "Link", 12),
)

DISAGREEMENT_COLUMNS = (
    ("severity", "Disagreement", 24),
    ("rule_evaluation", "Rule Evaluation", 20),
    ("llm_evaluation", "LLM Evaluation", 20),
    ("llm_confidence", "LLM Confidence", 16),
    ("llm_reason", "LLM Reason", 58),
    ("title", "Title", 48),
    ("country", "Country", 18),
    ("role_family", "Role", 24),
    ("institution", "Institution", 36),
    ("city", "City", 20),
    ("deadline", "Deadline", 15),
    ("url", "Link", 12),
)


@dataclass(frozen=True)
class LLMShadowReportRows:
    main: tuple[dict[str, Any], ...]
    llm_rescued: tuple[dict[str, Any], ...]
    disagreements: tuple[dict[str, Any], ...]


def _job_id(job: dict[str, Any]) -> str:
    return str(job.get("canonical_id") or job.get("source_record_id") or "").strip()


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _rule_recommendation(job: dict[str, Any]) -> str:
    calibrated = with_calibrated_evaluation(job)
    row = record_to_row(calibrated)
    return str(row.get("recommendation") or "").upper()


def _base_row(job: dict[str, Any]) -> dict[str, Any]:
    calibrated = with_calibrated_evaluation(job)
    row = record_to_row(calibrated)
    return {
        "seen_status": str(row.get("seen_status") or "SEEN").upper(),
        "title": _compact(row.get("title")),
        "country": _compact(row.get("country") or row.get("country_code")),
        "role_family": _compact(row.get("role_family")),
        "institution": _compact(row.get("institution")),
        "city": _compact(row.get("city")),
        "deadline": _compact(row.get("deadline")),
        "url": _compact(row.get("url")),
    }


def _full_record_map(records: Iterable[FullEvaluationRecord]) -> dict[tuple[str, str], FullEvaluationRecord]:
    out: dict[tuple[str, str], FullEvaluationRecord] = {}
    for row in records:
        out[(row.job_id, row.origin)] = row
    return out


def _llm_fields(record: FullEvaluationRecord | None) -> dict[str, Any]:
    if record is None:
        return {
            "llm_evaluation": "NOT_EVALUATED",
            "llm_confidence": "",
            "llm_reason": "",
        }
    result = record.evaluation.get("llm_result") if isinstance(record.evaluation, dict) else None
    result = result if isinstance(result, dict) else {}
    return {
        "llm_evaluation": str(result.get("decision") or "NOT_EVALUATED").upper(),
        "llm_confidence": result.get("confidence", ""),
        "llm_reason": _compact(result.get("reason_short")),
    }


def _agreement(rule: str, llm: str) -> str:
    if llm == "NOT_EVALUATED":
        return "NO_LLM_RESULT"
    if rule == llm:
        return "AGREEMENT"
    if rule not in RULE_RANK or llm not in LLM_RANK:
        return "UNCLASSIFIED"
    distance = abs(LLM_RANK[llm] - RULE_RANK[rule])
    return "MAJOR_DISAGREEMENT" if distance >= 2 else "MINOR_DISAGREEMENT"


def _sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("llm_evaluation") == "NOT_EVALUATED",
        str(row.get("rule_evaluation") or ""),
        str(row.get("llm_evaluation") or ""),
        str(row.get("country") or "").casefold(),
        str(row.get("title") or "").casefold(),
    )


def build_llm_shadow_report_rows(
    canonical_jobs: Iterable[dict[str, Any]],
    *,
    main_job_ids: Iterable[str],
    full_evaluation_records: Iterable[FullEvaluationRecord],
) -> LLMShadowReportRows:
    jobs_by_id = {
        _job_id(job): job
        for job in canonical_jobs
        if _job_id(job)
    }
    main_ids = {str(x).strip() for x in main_job_ids if str(x).strip()}
    evaluations = _full_record_map(full_evaluation_records)

    main_rows: list[dict[str, Any]] = []
    disagreement_rows: list[dict[str, Any]] = []
    for job_id in sorted(main_ids):
        job = jobs_by_id.get(job_id)
        if job is None:
            continue
        rule = _rule_recommendation(job)
        record = evaluations.get((job_id, ORIGIN_MAIN))
        row = {
            **_base_row(job),
            "rule_evaluation": rule,
            **_llm_fields(record),
        }
        row["agreement"] = _agreement(rule, row["llm_evaluation"])
        main_rows.append(row)

        if row["agreement"] in {"MINOR_DISAGREEMENT", "MAJOR_DISAGREEMENT"}:
            disagreement_rows.append(
                {
                    **row,
                    "severity": row["agreement"],
                }
            )

    rescued_rows: list[dict[str, Any]] = []
    for (job_id, origin), record in evaluations.items():
        if origin != ORIGIN_LLM_RESCUE:
            continue
        job = jobs_by_id.get(job_id)
        if job is None:
            continue
        llm = _llm_fields(record)
        if llm["llm_evaluation"] not in FAVORABLE_LLM_DECISIONS:
            continue
        rescued_rows.append(
            {
                **_base_row(job),
                "rule_evaluation": _rule_recommendation(job),
                **llm,
            }
        )

    main_rows.sort(key=_sort_key)
    rescued_rows.sort(key=_sort_key)
    disagreement_rows.sort(
        key=lambda row: (
            0 if row["severity"] == "MAJOR_DISAGREEMENT" else 1,
            str(row.get("title") or "").casefold(),
        )
    )

    return LLMShadowReportRows(
        main=tuple(main_rows),
        llm_rescued=tuple(rescued_rows),
        disagreements=tuple(disagreement_rows),
    )


def _write_sheet(
    workbook: xlsxwriter.Workbook,
    *,
    name: str,
    rows: Iterable[dict[str, Any]],
    columns: tuple[tuple[str, str, int], ...],
) -> None:
    rows = list(rows)
    ws = workbook.add_worksheet(name)
    ws.freeze_panes(1, 1)
    ws.hide_gridlines(2)
    ws.set_row(0, 28)

    header = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#1F4E78",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        }
    )
    text = workbook.add_format(
        {"text_wrap": True, "valign": "top", "border": 1, "border_color": "#D9E2F3"}
    )
    link = workbook.add_format(
        {
            "font_color": "#0563C1",
            "underline": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#D9E2F3",
        }
    )

    for col_idx, (_, label, width) in enumerate(columns):
        ws.write(0, col_idx, label, header)
        ws.set_column(col_idx, col_idx, width)

    for row_idx, row in enumerate(rows, start=1):
        ws.set_row(row_idx, 45)
        for col_idx, (key, _, _) in enumerate(columns):
            value = row.get(key, "")
            if key == "url" and value:
                try:
                    ws.write_url(row_idx, col_idx, str(value), link, string="Open")
                except Exception:
                    ws.write(row_idx, col_idx, str(value), text)
            else:
                ws.write(row_idx, col_idx, value, text)

    if rows:
        ws.autofilter(0, 0, len(rows), len(columns) - 1)


def build_llm_shadow_xlsx(
    canonical_jobs: Iterable[dict[str, Any]],
    output_path: Path,
    *,
    main_job_ids: Iterable[str],
    full_evaluation_records: Iterable[FullEvaluationRecord],
) -> Path:
    rows = build_llm_shadow_report_rows(
        canonical_jobs,
        main_job_ids=main_job_ids,
        full_evaluation_records=full_evaluation_records,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = xlsxwriter.Workbook(output_path)
    workbook.set_properties(
        {
            "title": "International Academic Job Search — LLM Shadow Report",
            "subject": "Rule and LLM shadow comparison",
            "comments": (
                f"Generated by {REPORT_VERSION}. MAIN preserves rule-found jobs; "
                "LLM_RESCUED contains favorable Rescue-only Full evaluations; "
                "DISAGREEMENTS contains MAIN rule-vs-LLM disagreements."
            ),
        }
    )
    _write_sheet(workbook, name="MAIN", rows=rows.main, columns=MAIN_COLUMNS)
    _write_sheet(workbook, name="LLM_RESCUED", rows=rows.llm_rescued, columns=RESCUED_COLUMNS)
    _write_sheet(workbook, name="DISAGREEMENTS", rows=rows.disagreements, columns=DISAGREEMENT_COLUMNS)
    workbook.close()
    return output_path


def load_full_evaluation_records(path: Path) -> list[FullEvaluationRecord]:
    rows: list[FullEvaluationRecord] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"line {line_no} is not an object")
        rows.append(
            FullEvaluationRecord(
                job_id=str(payload.get("job_id") or ""),
                origin=str(payload.get("origin") or ""),
                triage_id=payload.get("triage_id"),
                evaluation=payload.get("evaluation") if isinstance(payload.get("evaluation"), dict) else {},
            )
        )
    return rows
