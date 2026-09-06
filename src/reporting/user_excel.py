from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import xlsxwriter

from src.evaluation.calibrated_e021 import with_calibrated_evaluation
from src.evaluation.recall_first_e11 import evaluate_recall_first_e11
from src.reporting.report import record_to_row

USER_REPORT_VERSION = "USER_REPORT_V1.4.1_OPERATIONAL_ROLE_FILTER"
USER_PRIORITIES = ("STRONG_APPLY", "APPLY", "REVIEW")
PRIORITY_RANK = {value: index for index, value in enumerate(USER_PRIORITIES)}

# Apply identically to both sheets, before either evaluator can rescue a role.
# Match occupational identities at the start of the title, never JD keywords:
# a researcher studying drivers/security remains eligible for normal evaluation.
_OPERATIONAL_TITLE = re.compile(
    r"^(?:(?:senior|junior|lead|chief|principal)\s+)?(?:"
    r"(?:catering\s+)?(?:van|bus|delivery|truck|transport)\s+driver|"
    r"catering\s+(?:assistant|officer|manager)|"
    r"(?:it|information|cyber)\s+security\s+(?:lead|specialist|officer|manager|analyst|engineer)|"
    r"(?:systems?|network|school|faculty)\s+administrator|"
    r"(?:it|desktop|operational)\s+support\s+(?:officer|assistant|technician|specialist)|"
    r"education\s+partnerships\s+officer|hdr\s+engagement\s+manager|"
    r"social\s+media\s+(?:lead|manager|officer)|"
    r"student\s+(?:conduct\s+investigator|cultural\s+wellbeing\s+officer)|"
    r"site\s+reliability\s+engineer"
    r")\b", re.IGNORECASE,
)


def _excluded_operational_role(record: dict[str, Any]) -> bool:
    position = record.get("position") or {}
    title = position.get("title_raw") or position.get("title_normalized") or ""
    return bool(_OPERATIONAL_TITLE.search(" ".join(str(title).split())))
USER_COLUMNS = (
    ("recommendation", "Priority", 18),
    ("title", "Title", 48),
    ("country", "Country", 18),
    ("role_family", "Role", 24),
    ("institution", "Institution", 36),
    ("city", "City", 20),
    ("deadline", "Deadline", 15),
    ("url", "Link", 12),
)

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_MONTH_PATTERN = (
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _parsed_deadline(value: Any) -> str:
    text = _compact(value)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass

    iso_match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso_match:
        return iso_match.group(0)

    named_match = re.search(
        rf"\b(\d{{1,2}})(?:\s*(?:st|nd|rd|th))?[\s-]+{_MONTH_PATTERN}[\s,-]+(20\d{{2}})\b",
        text,
        re.IGNORECASE,
    )
    if named_match:
        month_text = named_match.group(2).lower()
        month = _MONTHS.get(month_text) or _MONTHS.get(month_text[:4]) or _MONTHS.get(month_text[:3])
        if month:
            try:
                return datetime(int(named_match.group(3)), month, int(named_match.group(1))).date().isoformat()
            except ValueError:
                pass

    numeric_match = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d{2})\b", text)
    if numeric_match:
        try:
            return datetime(
                int(numeric_match.group(3)),
                int(numeric_match.group(2)),
                int(numeric_match.group(1)),
            ).date().isoformat()
        except ValueError:
            pass
    return ""


def _deadline_parts(value: Any) -> tuple[int, str, str]:
    day = _parsed_deadline(value)
    if not day:
        return 1, "9999-12-31", ""
    return 0, day, day


def _full_jd(record: dict[str, Any]) -> str:
    description = record.get("description") if isinstance(record.get("description"), dict) else {}
    return str(description.get("full_jd") or "")


def _clean_institution(record: dict[str, Any], fallback: Any) -> str:
    position = record.get("position") if isinstance(record.get("position"), dict) else {}
    normalized = _compact(position.get("institution_normalized"))
    raw = _compact(position.get("institution_raw") or fallback)
    if normalized and len(normalized) <= 120:
        return normalized

    noisy = (
        len(raw) > 120
        or "EURAXESS" in raw
        or "Jobs & Opportunities" in raw
        or "ERA Talent Platform" in raw
    )
    if raw and not noisy:
        return raw

    full_jd = _full_jd(record)
    for pattern in (
        r"Organisation/Company\s+(.+?)(?=\s+(?:Department|Research Field|Researcher Profile|Positions|Application Deadline)\b)",
        r"Company/Institute\s+(.+?)(?=\s+(?:Country|City|Contact|Website|E-Mail|Phone|STATUS:)\b)",
    ):
        match = re.search(pattern, full_jd, re.IGNORECASE | re.DOTALL)
        if match:
            candidate = _compact(match.group(1))
            if 2 <= len(candidate) <= 120:
                return candidate
    return ""


def _clean_city(record: dict[str, Any], fallback: Any) -> str:
    direct = _compact(fallback)
    if direct:
        return direct

    full_jd = _full_jd(record)
    if "Work Location(s)" not in full_jd:
        return ""
    location_tail = full_jd.rsplit("Work Location(s)", 1)[-1]
    match = re.search(
        r"\bCity\s+(.+?)(?=\s+(?:Contact|Postal|Website|E-Mail|Phone|STATUS:)\b)",
        location_tail,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    candidate = _compact(match.group(1))
    return candidate if 1 <= len(candidate) <= 60 else ""


def build_user_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if _excluded_operational_role(record):
            continue
        calibrated_record = with_calibrated_evaluation(record)
        row = record_to_row(calibrated_record)
        priority = str(row.get("recommendation") or "").upper()
        lifecycle = str(row.get("lifecycle_status") or "UNKNOWN").upper()
        if priority not in PRIORITY_RANK or lifecycle == "CLOSED":
            continue
        _, deadline_sort, deadline_display = _deadline_parts(row.get("deadline"))
        clean = {
            "recommendation": priority,
            "title": _compact(row.get("title")),
            "country": _compact(row.get("country") or row.get("country_code")),
            "role_family": _compact(row.get("role_family")),
            "institution": _clean_institution(record, row.get("institution")),
            "city": _clean_city(record, row.get("city")),
            "deadline": deadline_display,
            "url": _compact(row.get("url")),
            "_deadline_sort": deadline_sort,
        }
        rows.append(clean)

    rows.sort(
        key=lambda row: (
            PRIORITY_RANK[row["recommendation"]],
            1 if not row["deadline"] else 0,
            row["_deadline_sort"],
            row["country"].casefold(),
            row["title"].casefold(),
            row["institution"].casefold(),
        )
    )
    for row in rows:
        row.pop("_deadline_sort", None)
    return rows


def load_canonical_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("canonical records must be a JSON array")
    return [item for item in data if isinstance(item, dict)]


REVIEW_COLUMNS = (("review_type", "Review type", 29),) + USER_COLUMNS[1:] + (
    ("review_reason", "Why review", 55),
    ("seen_status", "Change", 24),
)


def build_review_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Additional visibility only; never overrides JOBS or mutates production state."""
    rows = []
    seen = set()
    for record in records:
        if _excluded_operational_role(record):
            continue
        if build_user_rows([record]):
            continue
        row = record_to_row(record)
        if str(row.get("lifecycle_status") or "UNKNOWN").upper() == "CLOSED":
            continue
        result = evaluate_recall_first_e11(record)
        route = result.get("operational_route")
        if route not in {"JOBS", "NEEDS_DETAIL_REVIEW"}:
            continue
        identity = record.get("canonical_id") or (row.get("title"), row.get("url"))
        if identity in seen:
            continue
        seen.add(identity)
        _, _, deadline = _deadline_parts(row.get("deadline"))
        detail = route == "NEEDS_DETAIL_REVIEW"
        rows.append({
            "review_type": "NEEDS_DETAIL_REVIEW" if detail else "RESCUE_REVIEW",
            "title": _compact(row.get("title")),
            "country": _compact(row.get("country") or row.get("country_code")),
            "role_family": _compact(row.get("role_family")),
            "institution": _clean_institution(record, row.get("institution")),
            "city": _clean_city(record, row.get("city")),
            "deadline": deadline,
            "url": _compact(row.get("url")),
            "seen_status": _compact(row.get("seen_status")),
            "review_reason": (
                "Essential details are missing or delegated to another document; open the source to verify."
                if detail else "Excluded from JOBS by E0.2.1; retained by E1.1 for human review. Suitability is unconfirmed."
            ),
        })
    rows.sort(key=lambda r: (r["seen_status"] not in {"NEW", "MATERIALLY_CHANGED", "REOPENED"},
                             r["deadline"] or "9999-12-31", r["title"].casefold()))
    return rows


def build_user_xlsx(records: Iterable[dict[str, Any]], output_path: Path) -> Path:
    records = list(records)
    rows = build_user_rows(records)
    review_rows = build_review_rows(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = xlsxwriter.Workbook(output_path)
    workbook.set_properties(
        {
            "title": "International Academic Job Search",
            "subject": "Clean user-facing actionable vacancy list",
            "comments": f"Generated by {USER_REPORT_VERSION}; JOBS uses E0.2.1; REVIEW_MORE adds E1.1 disagreements and missing-detail cases. Neither sheet guarantees suitability.",
        }
    )

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
    text = workbook.add_format({"text_wrap": True, "valign": "top", "border": 1, "border_color": "#D9E2F3"})
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
    priority_formats = {
        "STRONG_APPLY": workbook.add_format(
            {"bold": True, "bg_color": "#C6EFCE", "font_color": "#006100", "align": "center", "valign": "vcenter", "border": 1, "border_color": "#A9D18E"}
        ),
        "APPLY": workbook.add_format(
            {"bold": True, "bg_color": "#D9EAF7", "font_color": "#1F4E78", "align": "center", "valign": "vcenter", "border": 1, "border_color": "#9DC3E6"}
        ),
        "REVIEW": workbook.add_format(
            {"bold": True, "bg_color": "#FFF2CC", "font_color": "#7F6000", "align": "center", "valign": "vcenter", "border": 1, "border_color": "#FFD966"}
        ),
    }

    for sheet_name, rows, columns in (("JOBS", rows, USER_COLUMNS), ("REVIEW_MORE", review_rows, REVIEW_COLUMNS)):
        ws = workbook.add_worksheet(sheet_name)
        ws.freeze_panes(1, 1)
        ws.set_row(0, 28)
        ws.hide_gridlines(2)
    
        for column_index, (_, label, width) in enumerate(columns):
            ws.write(0, column_index, label, header)
            ws.set_column(column_index, column_index, width)
    
        for row_index, row in enumerate(rows, start=1):
            ws.set_row(row_index, 60 if sheet_name == "REVIEW_MORE" else 30)
            priority = row.get("recommendation", "REVIEW")
            for column_index, (key, _, _) in enumerate(columns):
                value = row.get(key, "")
                if key == "recommendation":
                    ws.write(row_index, column_index, value, priority_formats[priority])
                elif key == "url":
                    if value:
                        try:
                            ws.write_url(row_index, column_index, str(value), link, string="Open")
                        except Exception:
                            ws.write(row_index, column_index, str(value), text)
                    else:
                        ws.write_blank(row_index, column_index, None, text)
                else:
                    ws.write(row_index, column_index, value, text)
    
        if rows:
            ws.autofilter(0, 0, len(rows), len(columns) - 1)
    
    workbook.close()
    return output_path
