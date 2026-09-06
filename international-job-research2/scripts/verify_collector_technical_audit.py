from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.live_shards import LINKEDIN_EUROPE_PARTITIONS
from src.runtime.production_sources import production_source_map

AUDIT = ROOT / "validation" / "collector_technical_audit_2026-09-06.json"
ALLOWED = {"BLOCKER", "MAJOR", "DEGRADED", "PROVISIONAL_PASS"}


def verify() -> None:
    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert data["status"] == "COMPLETE_REPAIR_REQUIRED"
    audited = data.get("sources") or []
    audited_ids = [row["source_id"] for row in audited]
    assert len(audited_ids) == len(set(audited_ids)), "duplicate audited source_id"

    production = production_source_map()
    production_ids = [spec.source_id for shard in production.values() for spec in shard]
    production_counts = Counter(production_ids)
    duplicates = {key: value for key, value in production_counts.items() if value > 1}
    expected_duplicates = {"linkedin_europe": len(LINKEDIN_EUROPE_PARTITIONS)}
    assert duplicates == expected_duplicates, (
        "runtime partition duplicates must be explicit and limited to LinkedIn Europe: "
        f"expected={expected_duplicates}, actual={duplicates}"
    )
    logical_production_ids = sorted(production_counts)
    assert sorted(audited_ids) == logical_production_ids, (
        "technical audit logical source set must exactly match production source map: "
        f"missing={sorted(set(logical_production_ids)-set(audited_ids))}, "
        f"extra={sorted(set(audited_ids)-set(logical_production_ids))}"
    )

    for row in audited:
        assert row.get("audit") in ALLOWED, row
        assert row.get("evidence"), row
        assert row.get("run_status") in {"OK", "PARTIAL", "ERROR"}, row
        assert isinstance(row.get("records"), int) and row["records"] >= 0, row

    counts = Counter(row["audit"] for row in audited)
    summary = data["summary"]
    assert summary["sources_audited"] == len(audited) == 30
    for status in ALLOWED:
        assert summary[status] == counts[status], (status, summary[status], counts[status])
    assert summary["certified"] == 0

    defects = data.get("systemic_defects") or []
    defect_ids = [row.get("id") for row in defects]
    assert len(defect_ids) == len(set(defect_ids)) and all(defect_ids)
    assert any(row.get("severity") == "BLOCKER" for row in defects)
    assert data["next_stage"] == "PHASE1_STAGE4_REPAIR_EXISTING_COLLECTORS"

    print("Collector technical audit verification: PASS")
    print(f"Logical production sources audited: {len(audited)}")
    print(f"LinkedIn Europe runtime partitions: {len(LINKEDIN_EUROPE_PARTITIONS)}")
    print("Audit counts:", dict(sorted(counts.items())))


if __name__ == "__main__":
    verify()
