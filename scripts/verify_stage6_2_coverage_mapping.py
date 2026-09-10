from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.coverage_mapping import build_coverage_mapping


def main() -> int:
    mapping = build_coverage_mapping()
    countries = mapping["country_rows"]
    checks = {
        "mapping_only_semantics": mapping["semantics"] == "MAPPING_ONLY_NO_COMPLETENESS_JUDGEMENT",
        "configured_country_count_preserved": mapping["country_count"] == 13,
        "country_execution_links_accounted": mapping["country_execution_link_count"]
        == sum(row["execution_count"] for row in countries.values()),
        "board_family_rows_accounted": len(mapping["board_family_rows"]) == 17,
        "institution_rows_accounted": len(mapping["institution_rows"]) == 18,
        "unresolved_geography_is_explicit": all(
            not row.get("configured_country_codes", [])
            for row in []
        ) if False else mapping["unresolved_geography_execution_count"]
        == len(mapping["unresolved_geography_executions"]),
        "country_overlap_summary_accounted": sum(
            int(family_count) * count
            for family_count, count in mapping["country_board_family_overlap_counts"].items()
        ) == sum(row["board_family_count"] for row in countries.values()),
        "no_single_board_explicit_country": mapping["all_explicit_countries_have_multi_board_overlap"],
        "country_rows_have_traceability": all(
            row["source_ids"] and row["board_families"] and row["shards"]
            for row in countries.values()
        ),
        "unresolved_rows_have_traceability": all(
            row["source_id"] and row["board_family"] and row["geography_mode"]
            for row in mapping["unresolved_geography_executions"]
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("Stage 6.2 coverage mapping verification failed: " + ", ".join(failed))
    print(json.dumps({
        "status": "PASS",
        "profile": "STAGE_6_2_COVERAGE_MAPPING",
        "checks": checks,
        "summary": {
            "country_count": mapping["country_count"],
            "country_execution_link_count": mapping["country_execution_link_count"],
            "board_family_count": len(mapping["board_family_rows"]),
            "institution_count": len(mapping["institution_rows"]),
            "unresolved_geography_execution_count": mapping["unresolved_geography_execution_count"],
            "country_board_family_overlap_counts": mapping["country_board_family_overlap_counts"],
        },
        "behavior": "READ_ONLY_MAPPING",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
