from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.recall_design import build_recall_measurement_design


def main() -> int:
    design = build_recall_measurement_design()
    checks = {
        "design_only_semantics": design["semantics"] == "DESIGN_ONLY_NO_RECALL_RESULT",
        "primary_metric_is_end_to_end_recall": design["primary_metric"]["name"] == "END_TO_END_VACANCY_RECALL",
        "primary_unit_is_unique_vacancy": design["primary_metric"]["unit"] == "UNIQUE_VACANCY",
        "reference_set_independent": design["reference_set_rules"]["independence"]
        == "REFERENCE_ACQUISITION_MUST_NOT_USE_PIPELINE_OUTPUT_OR_PIPELINE_COLLECTOR_CODE",
        "reference_roster_frozen_before_compare": design["reference_set_rules"]["roster_freeze"]
        == "REFERENCE_SOURCE_ROSTER_MUST_BE_FROZEN_BEFORE_COMPARISON_WITH_PIPELINE_OUTPUT",
        "anti_leakage_rule_present": design["reference_set_rules"]["anti_leakage_rule"]
        == "PIPELINE_MATCH_STATUS_MUST_BE ADDED ONLY AFTER REFERENCE ELIGIBILITY IS FROZEN",
        "prospective_window_is_14_days": design["time_design"]["measurement_days"] == 14,
        "capture_grace_is_48_hours": design["time_design"]["pipeline_capture_grace_hours"] == 48,
        "core_markets_are_primary": len(design["market_scope"]["primary_recall_markets"]) == 8,
        "opportunistic_markets_separate": len(design["market_scope"]["opportunistic_markets"]) == 5,
        "primary_role_families_frozen": len(design["role_scope"]["primary_denominator_families"]) == 7,
        "secondary_roles_not_in_primary_denominator": design["role_scope"]["secondary_treatment"]
        == "REPORT_SEPARATELY_NOT_IN_PRIMARY_DENOMINATOR_UNLESS_POLICY_ENABLED",
        "ambiguous_roles_fail_open_to_adjudication": design["role_scope"]["unknown_or_ambiguous_treatment"]
        == "MANUAL_ADJUDICATION_REQUIRED_NO_SILENT_EXCLUSION",
        "matching_implementation_deferred": design["matching_design"]["stage_7_1_status"]
        == "POLICY_DEFINED_IMPLEMENTATION_DEFERRED_TO_STAGE_7_3",
        "miss_taxonomy_defined": len(design["miss_attribution_design"]["categories"]) == 8,
        "source_changes_forbidden": design["stage_boundaries"]["source_changes_allowed_before_stage_8"] is False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("Stage 7.1 recall design verification failed: " + ", ".join(failed))

    print(json.dumps({
        "status": "PASS",
        "profile": "STAGE_7_1_RECALL_MEASUREMENT_DESIGN",
        "checks": checks,
        "summary": {
            "primary_metric": design["primary_metric"]["name"],
            "measurement_days": design["time_design"]["measurement_days"],
            "pipeline_capture_grace_hours": design["time_design"]["pipeline_capture_grace_hours"],
            "primary_market_count": len(design["market_scope"]["primary_recall_markets"]),
            "opportunistic_market_count": len(design["market_scope"]["opportunistic_markets"]),
            "primary_role_family_count": len(design["role_scope"]["primary_denominator_families"]),
            "miss_category_count": len(design["miss_attribution_design"]["categories"]),
        },
        "behavior": "READ_ONLY_DESIGN_VERIFICATION",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
