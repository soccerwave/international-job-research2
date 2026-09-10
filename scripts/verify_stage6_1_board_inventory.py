from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.board_inventory import build_current_board_inventory
from src.runtime.production_sources import production_source_map

PRODUCTION_WORKFLOW = ROOT / ".github" / "workflows" / "production.yml"


def _workflow_shards() -> set[str]:
    text = PRODUCTION_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r"matrix:\s*\n\s*shard:\s*\n(?P<body>(?:\s*-\s*[a-z0-9-]+\s*\n)+)",
        text,
    )
    if not match:
        raise AssertionError("production shard matrix not found")
    return {
        item.strip()
        for item in re.findall(r"^\s*-\s*([a-z0-9-]+)\s*$", match.group("body"), re.M)
    }


def main() -> int:
    inventory = build_current_board_inventory()
    source_map = production_source_map(limit=1)
    configured_shards = set(source_map)
    workflow_shards = _workflow_shards()

    checks = {
        "semantics_configured_wiring_only": inventory["semantics"] == "CONFIGURED_WIRING_ONLY",
        "production_shards_match_workflow": configured_shards == workflow_shards,
        "every_execution_has_metadata": all(
            row.get("board_family")
            and row.get("board_kind")
            and row.get("geography_mode")
            and row.get("source_id")
            and row.get("report_key")
            and row.get("shard_id")
            for row in inventory["executions"]
        ),
        "execution_count_matches_source_map": inventory["source_execution_count"]
        == sum(len(items) for items in source_map.values()),
        "source_ids_match_source_map": set(inventory["source_ids"])
        == {spec.source_id for items in source_map.values() for spec in items},
        "report_keys_match_source_map": set(inventory["report_keys"])
        == {spec.report_key for items in source_map.values() for spec in items},
        "institution_list_is_inventory_derived": set(inventory["institutions"])
        == {row["institution"] for row in inventory["executions"] if row.get("institution")},
        "country_list_is_inventory_derived": set(inventory["configured_country_codes"])
        == {
            code
            for row in inventory["executions"]
            for code in row.get("configured_country_codes", [])
        },
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("Stage 6.1 inventory verification failed: " + ", ".join(failed))

    result = {
        "status": "PASS",
        "profile": "STAGE_6_1_CURRENT_BOARD_INVENTORY",
        "checks": checks,
        "summary": {
            key: inventory[key]
            for key in (
                "production_shard_count",
                "source_execution_count",
                "unique_source_id_count",
                "unique_report_key_count",
                "board_family_count",
                "institution_specific_source_count",
                "institution_count",
                "configured_country_count",
                "configured_country_codes",
                "board_kind_counts",
                "geography_mode_counts",
            )
        },
        "behavior": "READ_ONLY_INVENTORY",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
