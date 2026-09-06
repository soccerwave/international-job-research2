from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from src.reporting.report import build_reporting_payload, build_xlsx, write_summary_json

BASELINE_EVENT = "BASELINE_EXISTING"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def mark_baseline_existing(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a reporting-only copy where first-bootstrap records are not today's NEW items.

    Durable Stage 8 state semantics remain untouched: the first authoritative observation
    still creates identities internally as NEW. Production presentation converts only the
    first successful bootstrap snapshot to BASELINE_EXISTING so the initial market inventory
    is visible without flooding TODAY_ACTIONABLE/Telegram as newly discovered vacancies.
    """
    baseline = copy.deepcopy(records)
    for record in baseline:
        raw_extra = record.setdefault("raw_extra", {})
        state = raw_extra.setdefault("state", {})
        state["seen_status"] = BASELINE_EVENT
        state["change_reasons"] = []
    return baseline


def rebuild_fresh_bootstrap_report(*, output_root: Path, run_id: str) -> dict[str, Any]:
    """Replace only production-facing report outputs for the first authoritative bootstrap."""
    preprod_dir = output_root / run_id / "preprod"
    production_dir = output_root / run_id / "production"
    production_dir.mkdir(parents=True, exist_ok=True)

    canonical = _load_json(preprod_dir / "canonical_records.json")
    preprod_summary = _load_json(preprod_dir / "preprod_summary.json")
    if not isinstance(canonical, list):
        raise RuntimeError("Fresh-bootstrap canonical_records.json is not a list")

    records = mark_baseline_existing(canonical)
    payload = build_reporting_payload(
        records,
        run_id=run_id,
        generated_at=str((preprod_summary.get("reporting") or {}).get("generated_at") or "") or None,
        state_summary=preprod_summary.get("state") or {},
        source_diagnostics=preprod_summary.get("source_diagnostics") or {},
    )
    payload["summary"]["bootstrap_mode"] = BASELINE_EVENT
    payload["summary"]["baseline_existing"] = len(records)

    report_path = build_xlsx(payload, production_dir / "academic_job_report.xlsx")
    summary_path = write_summary_json(payload, production_dir / "report_summary.json")
    return {
        "mode": BASELINE_EVENT,
        "records": len(records),
        "today_actionable": int(payload["summary"].get("today_actionable") or 0),
        "report": str(report_path),
        "report_summary": str(summary_path),
    }
