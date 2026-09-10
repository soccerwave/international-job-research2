from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.gap_register import build_evidence_gap_register


def main() -> int:
    register = build_evidence_gap_register()
    checks = {
        "register_only_semantics": register["semantics"] == "REGISTER_ONLY_NO_SOURCE_CHANGE",
        "all_stage6_3_findings_resolved": register["entry_count"] == 9,
        "one_confirmed_structural_gap": register["confirmed_structural_gap_count"] == 1,
        "confirmed_gap_is_uniroles": register["confirmed_structural_gap_ids"] == ["uniroles_au"],
        "five_recall_pending_items": register["recall_pending_count"] == 5,
        "three_not_gap_items": register["not_gap_count"] == 3,
        "no_source_change_allowed": register["source_change_allowed"] is False,
        "decision_boundary_preserved": register["next_decision_boundary"]
        == "AFTER_STAGE_7_RECALL_AND_STAGE_8_GAP_ANALYSIS",
        "every_entry_has_evidence": all(entry["evidence"] for entry in register["entries"]),
        "every_entry_has_disposition": all(entry["disposition"] for entry in register["entries"]),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("Stage 6.4 gap register verification failed: " + ", ".join(failed))

    print(json.dumps({
        "status": "PASS",
        "profile": "STAGE_6_4_EVIDENCE_GAP_REGISTER",
        "checks": checks,
        "summary": {
            "entry_count": register["entry_count"],
            "classification_counts": register["classification_counts"],
            "confirmed_structural_gap_ids": register["confirmed_structural_gap_ids"],
            "recall_pending_ids": register["recall_pending_ids"],
            "not_gap_ids": register["not_gap_ids"],
        },
        "behavior": "READ_ONLY_REGISTER",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
