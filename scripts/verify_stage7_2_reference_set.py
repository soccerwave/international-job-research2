from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.reference_set import (
    CORE_MARKETS,
    MANIFEST_PATH,
    ROSTER_PATH,
    SCHEMA_PATH,
    build_reference_construction_status,
)

RECORDS_PATH = ROOT / "data" / "reference" / "stage7" / "reference_observations_v1.jsonl"


def main() -> int:
    status = build_reference_construction_status()
    checks = {
        "roster_file_exists": ROSTER_PATH.exists(),
        "manifest_file_exists": MANIFEST_PATH.exists(),
        "schema_file_exists": SCHEMA_PATH.exists(),
        "records_file_exists": RECORDS_PATH.exists(),
        "sixteen_reference_sources": status["reference_source_count"] == 16,
        "eight_core_markets": status["core_market_count"] == 8,
        "two_sources_per_core_market": status["all_core_markets_have_two_sources"],
        "no_duplicate_reference_source_ids": status["duplicate_source_id_count"] == 0,
        "no_duplicate_reference_urls": status["duplicate_url_count"] == 0,
        "source_roster_frozen": status["source_roster_frozen"] is True,
        "reference_set_not_prematurely_frozen": status["reference_set_frozen"] is False,
        "collection_status_active": status["status"] == "ACTIVE_COLLECTION",
        "window_is_fourteen_days": status["window"]["measurement_days"] == 14,
        "window_dates_locked": status["window"]["start_date"] == "2026-09-10"
        and status["window"]["end_date"] == "2026-09-23"
        and status["window"]["capture_grace_end_date"] == "2026-09-25",
        "daily_capture_cadence": status["capture_policy"]["cadence"] == "DAILY",
        "pipeline_output_forbidden": status["capture_policy"]["pipeline_output_allowed"] is False,
        "pipeline_collector_code_forbidden": status["capture_policy"]["pipeline_collector_code_allowed"] is False,
        "comparison_forbidden_before_freeze": status["capture_policy"]["comparison_with_pipeline_allowed_before_reference_freeze"] is False,
        "eligibility_freeze_before_matching": status["capture_policy"]["reference_eligibility_must_be_frozen_before_matching"] is True,
        "reference_schema_has_no_pipeline_match_fields": status["schema_forbidden_match_fields_present"] == [],
        "initial_reference_record_count_zero": status["current_record_count"] == 0,
        "all_market_keys_present": set(status["country_source_counts"]) == set(CORE_MARKETS),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("Stage 7.2 reference-set construction verification failed: " + ", ".join(failed))

    result = {
        "status": "PASS",
        "profile": "STAGE_7_2_REFERENCE_SET_CONSTRUCTION_SETUP",
        "checks": checks,
        "summary": {
            "reference_source_count": status["reference_source_count"],
            "country_source_counts": status["country_source_counts"],
            "relation_counts": status["relation_counts"],
            "window": status["window"],
            "current_record_count": status["current_record_count"],
            "reference_set_status": status["status"],
            "reference_set_frozen": status["reference_set_frozen"],
        },
        "behavior": "REFERENCE_COLLECTION_SETUP_ONLY",
        "stage7_2_done": False,
        "stage7_2_done_condition": status["stage7_2_done_condition"],
        "next_action": status["next_action"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
