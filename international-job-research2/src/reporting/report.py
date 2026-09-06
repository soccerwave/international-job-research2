from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import xlsxwriter

from src.reporting import REPORTING_VERSION

RECOMMENDATION_ORDER = ("STRONG_APPLY", "APPLY", "REVIEW", "LOW_PRIORITY", "SKIP")
ACTIONABLE = {"STRONG_APPLY", "APPLY", "REVIEW"}
CHANGE_EVENTS = {"NEW", "MATERIALLY_CHANGED", "REOPENED"}
REVIEW_DISPOSITIONS = {"NEEDS_DETAIL_REVIEW", "POLICY_REVIEW"}
GOOD_DETAIL = {"FULL", "PARTIAL"}

JOB_COLUMNS = [
    ("recommendation", "Priority", 16),
    ("seen_status", "State event", 20),
    ("title", "Title", 40),
    ("institution", "Institution", 30),
    ("department", "Department", 28),
    ("country", "Country", 16),
    ("city", "City", 18),
    ("role_family", "Role", 24),
    ("scientific", "Scientific fit", 16),
    ("level", "Level fit", 14),
    ("methods", "Methods", 14),
    ("language", "Language", 14),
    ("mobility", "Mobility", 14),
    ("contract_fit", "Contract", 14),
    ("deadline", "Deadline", 15),
    ("detail_status", "Full JD", 14),
    ("source", "Source", 22),
    ("review_codes", "Review codes", 36),
    ("blocker_codes", "Blockers", 30),
    ("reason", "Evaluator reason", 62),
    ("url", "URL", 46),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _evaluation(record: dict[str, Any]) -> dict[str, Any]:
    direct = record.get("evaluation")
    if isinstance(direct, dict):
        return direct
    raw = record.get("raw_extra") or {}
    nested = raw.get("evaluation")
    return nested if isinstance(nested, dict) else {}


def _state(record: dict[str, Any]) -> dict[str, Any]:
    raw = record.get("raw_extra") or {}
    value = raw.get("state")
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value if str(item).strip())
    return str(value)


def _best_url(record: dict[str, Any]) -> str:
    source = record.get("source") or {}
    return str(source.get("apply_url") or source.get("detail_url") or source.get("listing_url") or "")


def record_to_row(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source") or {}
    position = record.get("position") or {}
    location = record.get("location") or {}
    dates = record.get("dates") or {}
    description = record.get("description") or {}
    evaluation = _evaluation(record)
    state = _state(record)
    dims = evaluation.get("dimensions") if isinstance(evaluation.get("dimensions"), dict) else {}
    recommendation = str(evaluation.get("recommendation") or "REVIEW").upper()
    disposition = str(evaluation.get("pre_evaluation_disposition") or "").upper()
    source_status = str(source.get("source_status") or "UNKNOWN").upper()
    lifecycle = str(state.get("lifecycle_status") or source_status or "UNKNOWN").upper()
    return {
        "canonical_id": str(record.get("canonical_id") or ""),
        "source_record_id": str(record.get("source_record_id") or ""),
        "recommendation": recommendation,
        "pre_evaluation_disposition": disposition,
        "seen_status": str(state.get("seen_status") or "").upper(),
        "quality_events": _text(state.get("quality_events") or []),
        "change_reasons": _text(state.get("change_reasons") or []),
        "title": str(position.get("title_raw") or position.get("title_normalized") or ""),
        "institution": str(position.get("institution_raw") or position.get("institution_normalized") or ""),
        "department": str(position.get("department") or ""),
        "country": str(location.get("country_name") or location.get("country_code") or ""),
        "country_code": str(location.get("country_code") or "").upper(),
        "city": str(location.get("city") or ""),
        "role_family": str(evaluation.get("role_family") or position.get("role_family") or ""),
        "role_level": str(position.get("role_level") or ""),
        "scientific": str(dims.get("scientific") or ""),
        "level": str(dims.get("level") or ""),
        "methods": str(dims.get("methods") or ""),
        "language": str(dims.get("language") or ""),
        "mobility": str(dims.get("mobility") or ""),
        "registration": str(dims.get("registration") or ""),
        "contract_fit": str(dims.get("contract") or ""),
        "deadline": str(dates.get("deadline_at") or dates.get("deadline_text") or ""),
        "deadline_status": str(dates.get("deadline_status") or "UNKNOWN").upper(),
        "detail_status": str(description.get("detail_status") or "NOT_ATTEMPTED").upper(),
        "source": str(source.get("provider") or source.get("source_key") or ""),
        "source_key": str(source.get("source_key") or ""),
        "source_status": source_status,
        "lifecycle_status": lifecycle,
        "review_codes": _text(evaluation.get("review_codes") or []),
        "blocker_codes": _text(evaluation.get("blocker_codes") or []),
        "fit_signals": _text(evaluation.get("fit_signals") or []),
        "reason": str(evaluation.get("reason") or ""),
        "url": _best_url(record),
    }


def _is_open(row: dict[str, Any]) -> bool:
    return str(row.get("lifecycle_status") or "UNKNOWN").upper() != "CLOSED"


def _is_review_queue(row: dict[str, Any]) -> bool:
    return (
        row.get("recommendation") == "REVIEW"
        or row.get("pre_evaluation_disposition") in REVIEW_DISPOSITIONS
        or row.get("detail_status") not in GOOD_DETAIL
    ) and _is_open(row)


def _source_rows(rows: list[dict[str, Any]], source_diagnostics: dict[str, Any] | None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("source_key") or row.get("source") or "unknown")].append(row)
    diagnostics = source_diagnostics or {}
    output: list[dict[str, Any]] = []
    for source_key in sorted(grouped):
        items = grouped[source_key]
        diag = diagnostics.get(source_key) if isinstance(diagnostics, dict) else None
        diag = diag if isinstance(diag, dict) else {}
        rec = Counter(item["recommendation"] for item in items)
        output.append({
            "source_key": source_key,
            "status": str(diag.get("status") or "UNKNOWN").upper(),
            "observed": len(items),
            "actionable": sum(1 for item in items if item["recommendation"] in ACTIONABLE and _is_open(item)),
            "strong_apply": rec.get("STRONG_APPLY", 0),
            "apply": rec.get("APPLY", 0),
            "review": rec.get("REVIEW", 0),
            "detail_full_or_partial": sum(1 for item in items if item["detail_status"] in GOOD_DETAIL),
            "detail_unresolved": sum(1 for item in items if item["detail_status"] not in GOOD_DETAIL),
            "error": str(diag.get("error") or ""),
            "warnings": _text(diag.get("warnings") or []),
        })
    for source_key, diag in sorted(diagnostics.items()) if isinstance(diagnostics, dict) else []:
        if source_key in grouped or not isinstance(diag, dict):
            continue
        output.append({
            "source_key": source_key,
            "status": str(diag.get("status") or "UNKNOWN").upper(),
            "observed": 0,
            "actionable": 0,
            "strong_apply": 0,
            "apply": 0,
            "review": 0,
            "detail_full_or_partial": 0,
            "detail_unresolved": 0,
            "error": str(diag.get("error") or ""),
            "warnings": _text(diag.get("warnings") or []),
        })
    return output


def build_reporting_payload(
    records: Iterable[dict[str, Any]],
    *,
    run_id: str,
    generated_at: str | None = None,
    state_summary: dict[str, Any] | None = None,
    source_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = [record_to_row(record) for record in records]
    actionable = [row for row in rows if row["recommendation"] in ACTIONABLE and _is_open(row)]
    today = [row for row in actionable if row["seen_status"] in CHANGE_EVENTS]
    review_queue = [row for row in rows if _is_review_queue(row)]
    low = [row for row in rows if row["recommendation"] == "LOW_PRIORITY" and _is_open(row)]
    audit = list(rows)
    rec_counts = Counter(row["recommendation"] for row in rows)
    event_counts = Counter(row["seen_status"] for row in rows if row["seen_status"])
    country_counts = Counter(row["country"] or row["country_code"] or "Unknown" for row in actionable)
    sources = _source_rows(rows, source_diagnostics)
    source_health = Counter(row["status"] for row in sources)
    state_summary = state_summary or {}

    summary = {
        "reporting_version": REPORTING_VERSION,
        "run_id": run_id,
        "generated_at": generated_at or _now_iso(),
        "records_observed": len(rows),
        "current_actionable": len(actionable),
        "today_actionable": len(today),
        "review_queue": len(review_queue),
        "low_priority": len(low),
        "skipped": rec_counts.get("SKIP", 0),
        "recommendations": {key: rec_counts.get(key, 0) for key in RECOMMENDATION_ORDER},
        "events": {key: event_counts.get(key, 0) for key in ("NEW", "SEEN", "MATERIALLY_CHANGED", "REOPENED")},
        "quality_events": {
            "DETAIL_RESOLVED": int(state_summary.get("DETAIL_RESOLVED", 0) or 0),
            "DETAIL_UNRESOLVED": int(state_summary.get("DETAIL_UNRESOLVED", 0) or 0),
        },
        "state_generation": state_summary.get("generation"),
        "state_jobs": state_summary.get("state_jobs"),
        "source_health": {key: source_health.get(key, 0) for key in ("OK", "PARTIAL", "ERROR", "UNKNOWN")},
        "top_actionable_countries": country_counts.most_common(10),
    }
    return {
        "summary": summary,
        "today_actionable": today,
        "current_actionable": actionable,
        "review_queue": review_queue,
        "low_priority": low,
        "audit": audit,
        "sources": sources,
    }


def _write_jobs_sheet(workbook, name: str, rows: list[dict[str, Any]], formats: dict[str, Any]) -> None:
    ws = workbook.add_worksheet(name[:31])
    ws.freeze_panes(1, 2)
    for col, (_, label, width) in enumerate(JOB_COLUMNS):
        ws.write(0, col, label, formats["header"])
        ws.set_column(col, col, width)
    priority_formats = {
        "STRONG_APPLY": formats["strong"],
        "APPLY": formats["apply"],
        "REVIEW": formats["review"],
        "LOW_PRIORITY": formats["low"],
        "SKIP": formats["skip"],
    }
    for r, row in enumerate(rows, start=1):
        for c, (key, _, _) in enumerate(JOB_COLUMNS):
            value = row.get(key, "")
            cell_fmt = priority_formats.get(row.get("recommendation"), formats["text"]) if c == 0 else formats["text"]
            if key == "url" and value:
                try:
                    ws.write_url(r, c, str(value), formats["link"], string="Open vacancy")
                except Exception:
                    ws.write(r, c, str(value), formats["text"])
            else:
                ws.write(r, c, value, cell_fmt)
    if rows:
        ws.autofilter(0, 0, len(rows), len(JOB_COLUMNS) - 1)
    ws.set_default_row(32)


def build_xlsx(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload["summary"]
    workbook = xlsxwriter.Workbook(output_path)
    workbook.set_properties({
        "title": "International Academic Job Search Report",
        "subject": "Human-review academic vacancy report",
        "comments": f"Generated by {REPORTING_VERSION}",
    })
    formats = {
        "title": workbook.add_format({"bold": True, "font_size": 18}),
        "section": workbook.add_format({"bold": True, "font_size": 11, "bottom": 1}),
        "header": workbook.add_format({"bold": True, "border": 1, "text_wrap": True, "valign": "vcenter"}),
        "text": workbook.add_format({"text_wrap": True, "valign": "top"}),
        "link": workbook.add_format({"font_color": "blue", "underline": True, "valign": "top"}),
        "int": workbook.add_format({"num_format": "0"}),
        "strong": workbook.add_format({"bold": True, "bg_color": "#C6EFCE", "font_color": "#006100"}),
        "apply": workbook.add_format({"bold": True, "bg_color": "#D9EAF7"}),
        "review": workbook.add_format({"bold": True, "bg_color": "#FFF2CC"}),
        "low": workbook.add_format({"bg_color": "#E7E6E6"}),
        "skip": workbook.add_format({"bg_color": "#F4CCCC", "font_color": "#7F0000"}),
    }

    ws = workbook.add_worksheet("SUMMARY")
    ws.set_column("A:A", 34)
    ws.set_column("B:B", 18)
    ws.set_column("D:D", 22)
    ws.set_column("E:E", 12)
    ws.write("A1", "International Academic Job Search", formats["title"])
    ws.write("A3", "Run overview", formats["section"])
    overview = [
        ("Reporting version", summary.get("reporting_version")),
        ("Run ID", summary.get("run_id")),
        ("Generated at", summary.get("generated_at")),
        ("Records observed", summary.get("records_observed", 0)),
        ("Current actionable", summary.get("current_actionable", 0)),
        ("Today's actionable changes", summary.get("today_actionable", 0)),
        ("Review queue", summary.get("review_queue", 0)),
        ("Low priority", summary.get("low_priority", 0)),
        ("Skipped", summary.get("skipped", 0)),
        ("State generation", summary.get("state_generation") or ""),
        ("Durable state jobs", summary.get("state_jobs") or ""),
    ]
    for idx, (label, value) in enumerate(overview, start=3):
        ws.write(idx, 0, label)
        if isinstance(value, int):
            ws.write_number(idx, 1, value, formats["int"])
        else:
            ws.write(idx, 1, value or "")

    ws.write("D3", "Recommendation", formats["section"])
    ws.write("E3", "Count", formats["section"])
    rec = summary.get("recommendations") or {}
    for i, key in enumerate(RECOMMENDATION_ORDER, start=4):
        ws.write(i - 1, 3, key)
        ws.write_number(i - 1, 4, int(rec.get(key, 0) or 0), formats["int"])
    chart = workbook.add_chart({"type": "column"})
    chart.add_series({
        "name": "Recommendations",
        "categories": "=SUMMARY!$D$4:$D$8",
        "values": "=SUMMARY!$E$4:$E$8",
    })
    chart.set_title({"name": "Recommendation distribution"})
    chart.set_legend({"none": True})
    chart.set_size({"width": 520, "height": 280})
    ws.insert_chart("G3", chart)

    ws.write("D11", "State event", formats["section"])
    ws.write("E11", "Count", formats["section"])
    events = summary.get("events") or {}
    for i, key in enumerate(("NEW", "SEEN", "MATERIALLY_CHANGED", "REOPENED"), start=12):
        ws.write(i - 1, 3, key)
        ws.write_number(i - 1, 4, int(events.get(key, 0) or 0), formats["int"])

    ws.write("A17", "Top actionable countries", formats["section"])
    ws.write("A18", "Country", formats["header"])
    ws.write("B18", "Count", formats["header"])
    for i, item in enumerate(summary.get("top_actionable_countries") or [], start=19):
        country, count = item
        ws.write(i - 1, 0, country)
        ws.write_number(i - 1, 1, int(count), formats["int"])

    ws.write("D17", "Source health", formats["section"])
    ws.write("D18", "Status", formats["header"])
    ws.write("E18", "Count", formats["header"])
    health = summary.get("source_health") or {}
    for i, key in enumerate(("OK", "PARTIAL", "ERROR", "UNKNOWN"), start=19):
        ws.write(i - 1, 3, key)
        ws.write_number(i - 1, 4, int(health.get(key, 0) or 0), formats["int"])

    _write_jobs_sheet(workbook, "TODAY_ACTIONABLE", payload["today_actionable"], formats)
    _write_jobs_sheet(workbook, "CURRENT_ACTIONABLE", payload["current_actionable"], formats)
    _write_jobs_sheet(workbook, "REVIEW_QUEUE", payload["review_queue"], formats)
    _write_jobs_sheet(workbook, "LOW_PRIORITY", payload["low_priority"], formats)
    _write_jobs_sheet(workbook, "AUDIT", payload["audit"], formats)

    src = workbook.add_worksheet("SOURCES")
    source_columns = [
        ("source_key", "Source", 26), ("status", "Health", 12), ("observed", "Observed", 11),
        ("actionable", "Actionable", 11), ("strong_apply", "Strong", 9), ("apply", "Apply", 9),
        ("review", "Review", 9), ("detail_full_or_partial", "Detail OK", 11),
        ("detail_unresolved", "Detail unresolved", 16), ("error", "Error", 42), ("warnings", "Warnings", 46),
    ]
    for c, (_, label, width) in enumerate(source_columns):
        src.write(0, c, label, formats["header"])
        src.set_column(c, c, width)
    for r, row in enumerate(payload["sources"], start=1):
        for c, (key, _, _) in enumerate(source_columns):
            src.write(r, c, row.get(key, ""), formats["text"])
    src.freeze_panes(1, 0)
    if payload["sources"]:
        src.autofilter(0, 0, len(payload["sources"]), len(source_columns) - 1)

    workbook.close()
    return output_path


def write_summary_json(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload["summary"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path
