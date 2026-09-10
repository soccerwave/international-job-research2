from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.board_inventory import build_current_board_inventory
from src.runtime.coverage_mapping import build_coverage_mapping
from src.runtime.structural_completeness import build_structural_completeness_checks
from src.runtime.gap_register import build_evidence_gap_register

FREEZE = ROOT / "RELEASE_FREEZE_V1.1.0.json"


def main() -> int:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    board = freeze["board_completeness"]

    inventory = build_current_board_inventory()
    mapping = build_coverage_mapping()
    structural = build_structural_completeness_checks()
    register = build_evidence_gap_register()

    checks = {
        "stage6_1_frozen": board.get("current_board_inventory") == "GITHUB_ACTIONS_VALIDATED_STAGE_6_1",
        "stage6_2_frozen": board.get("coverage_mapping") == "GITHUB_ACTIONS_VALIDATED_STAGE_6_2",
        "stage6_3_frozen": board.get("structural_completeness") == "GITHUB_ACTIONS_VALIDATED_STAGE_6_3",
        "stage6_4_frozen": board.get("gap_register") == "GITHUB_ACTIONS_VALIDATED_STAGE_6_4",
        "inventory_semantics_preserved": inventory["semantics"] == "CONFIGURED_WIRING_ONLY",
        "mapping_semantics_preserved": mapping["semantics"] == "MAPPING_ONLY_NO_COMPLETENESS_JUDGEMENT",
        "structural_semantics_preserved": structural["semantics"] == "STRUCTURAL_AUDIT_ONLY_NO_GAP_VERDICT",
        "register_semantics_preserved": register["semantics"] == "REGISTER_ONLY_NO_SOURCE_CHANGE",
        "production_shard_count_consistent": inventory["production_shard_count"] == board["production_shard_count"] == 17,
        "source_execution_count_consistent": inventory["source_execution_count"] == board["source_execution_count"] == 33,
        "configured_country_count_consistent": inventory["configured_country_count"] == mapping["country_count"] == board["configured_country_count"] == 13,
        "country_execution_links_consistent": mapping["country_execution_link_count"] == board["country_execution_link_count"] == 58,
        "no_target_country_without_explicit_wiring": structural["target_countries_without_explicit_wiring"] == [],
        "all_registered_tenants_wired": structural["unwired_registered_tenant_count"] == 0,
        "all_linkedin_partitions_wired": structural["unwired_linkedin_partition_count"] == 0,
        "gap_register_resolves_all_structural_findings": register["entry_count"] == structural["review_finding_count"] + structural["info_finding_count"] == 9,
        "single_confirmed_structural_gap_preserved": register["confirmed_structural_gap_ids"] == ["uniroles_au"],
        "recall_pending_boundary_preserved": set(register["recall_pending_ids"]) == {"jobs_ac_uk", "academics_de", "ecss", "dvs", "fens"},
        "no_source_change_authorized": register["source_change_allowed"] is False,
        "post_recall_decision_boundary_preserved": register["next_decision_boundary"] == "AFTER_STAGE_7_RECALL_AND_STAGE_8_GAP_ANALYSIS",
    }

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("Stage 6.5 board completeness certification failed: " + ", ".join(failed))

    result = {
        "status": "PASS",
        "profile": "STAGE_6_BOARD_COMPLETENESS_CERTIFICATION",
        "checks": checks,
        "summary": {
            "production_shard_count": inventory["production_shard_count"],
            "source_execution_count": inventory["source_execution_count"],
            "configured_country_count": inventory["configured_country_count"],
            "country_execution_link_count": mapping["country_execution_link_count"],
            "confirmed_structural_gap_ids": register["confirmed_structural_gap_ids"],
            "recall_pending_ids": register["recall_pending_ids"],
            "not_gap_ids": register["not_gap_ids"],
        },
        "behavior": "READ_ONLY_CERTIFICATION",
        "stage6_scope": "BOARD_COMPLETENESS_STRUCTURE_ONLY",
        "next_stage": "STAGE_7_RECALL_MEASUREMENT",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
