from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MARKETS = ROOT / "config" / "markets.json"
ROLES = ROOT / "config" / "roles.json"
DECISION = ROOT / "config" / "decision_policy.json"


def build_recall_measurement_design() -> dict[str, Any]:
    markets = json.loads(MARKETS.read_text(encoding="utf-8"))
    roles = json.loads(ROLES.read_text(encoding="utf-8"))
    decision = json.loads(DECISION.read_text(encoding="utf-8"))

    core_market_codes = [row["country_code"] for row in markets["core_markets"]]
    opportunistic_market_codes = [row["country_code"] for row in markets["opportunistic_markets"]]
    primary_role_families = list(roles["primary_families"])
    secondary_role_families = list(roles["secondary_families"])

    return {
        "version": 1,
        "stage": "7.1",
        "profile": "RECALL_MEASUREMENT_DESIGN",
        "semantics": "DESIGN_ONLY_NO_RECALL_RESULT",
        "governing_policy_ids": {
            "market_policy": markets["policy_id"],
            "role_policy": roles["policy_id"],
            "decision_policy": decision["policy_id"],
        },
        "measurement_objective": (
            "Estimate how many independently observed in-scope vacancies the production pipeline discovers, "
            "with primary emphasis on avoiding false negatives."
        ),
        "primary_metric": {
            "name": "END_TO_END_VACANCY_RECALL",
            "unit": "UNIQUE_VACANCY",
            "numerator": "UNIQUE_ELIGIBLE_REFERENCE_VACANCIES_MATCHED_TO_PIPELINE",
            "denominator": "UNIQUE_ELIGIBLE_REFERENCE_VACANCIES",
            "formula": "matched_unique_eligible_reference_vacancies / unique_eligible_reference_vacancies",
            "duplicate_rule": "SAME_VACANCY_COUNTS_ONCE_ACROSS_REFERENCE_SOURCES",
        },
        "secondary_metrics": [
            {
                "name": "SOURCE_OBSERVATION_RECALL",
                "unit": "REFERENCE_SOURCE_VACANCY_OBSERVATION",
                "purpose": "Locate board/source-level discovery misses without changing the primary denominator.",
            },
            {
                "name": "COUNTRY_RECALL",
                "unit": "UNIQUE_VACANCY",
                "purpose": "Break down end-to-end recall by market.",
            },
            {
                "name": "ROLE_FAMILY_RECALL",
                "unit": "UNIQUE_VACANCY",
                "purpose": "Break down end-to-end recall by normalized primary role family.",
            },
            {
                "name": "INSTITUTION_RECALL",
                "unit": "UNIQUE_VACANCY",
                "purpose": "Break down end-to-end recall for institutions represented in the reference set.",
            },
        ],
        "market_scope": {
            "primary_recall_markets": core_market_codes,
            "opportunistic_markets": opportunistic_market_codes,
            "opportunistic_treatment": "REPORT_SEPARATELY_NOT_IN_PRIMARY_AGGREGATE",
            "excluded_markets": [row["country_code"] for row in markets["excluded_markets"]],
        },
        "role_scope": {
            "primary_denominator_families": primary_role_families,
            "conditional_titles": "ADJUDICATE_USING_FROZEN_ROLE_POLICY_BEFORE_DENOMINATOR_ENTRY",
            "secondary_families": secondary_role_families,
            "secondary_treatment": "REPORT_SEPARATELY_NOT_IN_PRIMARY_DENOMINATOR_UNLESS_POLICY_ENABLED",
            "out_of_scope_treatment": "EXCLUDE_FROM_DENOMINATOR_WITH_REASON",
            "unknown_or_ambiguous_treatment": "MANUAL_ADJUDICATION_REQUIRED_NO_SILENT_EXCLUSION",
        },
        "reference_set_rules": {
            "independence": "REFERENCE_ACQUISITION_MUST_NOT_USE_PIPELINE_OUTPUT_OR_PIPELINE_COLLECTOR_CODE",
            "roster_freeze": "REFERENCE_SOURCE_ROSTER_MUST_BE_FROZEN_BEFORE_COMPARISON_WITH_PIPELINE_OUTPUT",
            "provenance_required": True,
            "minimum_reference_fields": [
                "reference_id",
                "reference_source",
                "reference_url",
                "observed_at",
                "title",
                "institution",
                "country_code",
                "posted_at_or_null",
                "deadline_at_or_null",
                "role_family_or_pending",
                "eligibility_status",
                "eligibility_reason",
            ],
            "eligibility_statuses": [
                "ELIGIBLE_PRIMARY",
                "ELIGIBLE_OPPORTUNISTIC",
                "OUT_OF_SCOPE",
                "PENDING_ADJUDICATION",
            ],
            "anti_leakage_rule": "PIPELINE_MATCH_STATUS_MUST_BE ADDED ONLY AFTER REFERENCE ELIGIBILITY IS FROZEN",
        },
        "time_design": {
            "mode": "PROSPECTIVE_FIXED_WINDOW",
            "measurement_days": 14,
            "reason": "COVERS_TWO_FULL_WEEK_CYCLES_AND_MATCHES_THE_EXISTING_14_DAY_LINKEDIN_DISCOVERY_HORIZON",
            "primary_cohort": "NEW_VACANCIES_POSTED_DURING_WINDOW",
            "active_stock_cohort": "VACANCIES_ALREADY_OPEN_AT_WINDOW_START_REPORTED_SEPARATELY",
            "unknown_posted_date_cohort": "FIRST_OBSERVED_DURING_WINDOW_REPORTED_SEPARATELY",
            "pipeline_capture_grace_hours": 48,
            "capture_grace_rule": "REFERENCE_VACANCY_COUNTS_AS_MATCHED_IF_PIPELINE_OBSERVES_IT_WITHIN_48_HOURS_OF_REFERENCE_OBSERVATION_OR_BEFORE_DEADLINE_IF_SOONER",
        },
        "matching_design": {
            "stage_7_1_status": "POLICY_DEFINED_IMPLEMENTATION_DEFERRED_TO_STAGE_7_3",
            "match_priority": [
                "EXACT_NORMALIZED_DETAIL_OR_APPLY_URL",
                "EXACT_SOURCE_JOB_ID_WHEN_SOURCE_COMPARABLE",
                "DETERMINISTIC_TITLE_INSTITUTION_COUNTRY_COMPOSITE",
                "MANUAL_REVIEW_FOR_AMBIGUOUS_CANDIDATES",
            ],
            "automatic_nonmatch_on_title_only": True,
            "many_reference_observations_to_one_vacancy_allowed": True,
        },
        "miss_attribution_design": {
            "stage_7_1_status": "TAXONOMY_DEFINED_IMPLEMENTATION_DEFERRED_TO_STAGE_7_5",
            "categories": [
                "SOURCE_NOT_COVERED",
                "QUERY_DISCOVERY_MISS",
                "PAGINATION_OR_LISTING_DISCOVERY_MISS",
                "PARSER_OR_EXTRACTION_MISS",
                "PRE_EVALUATION_FILTER_MISS",
                "TRANSIENT_RUNTIME_FAILURE",
                "MATCHING_OR_DEDUPLICATION_ISSUE",
                "UNKNOWN_REQUIRES_REVIEW",
            ],
            "unknown_is_allowed": True,
            "unknown_is_not_reclassified_as_success": True,
        },
        "reporting_design": {
            "primary_aggregate": "CORE_MARKETS_PRIMARY_ROLE_FAMILIES",
            "required_breakdowns": [
                "country_code",
                "reference_source",
                "role_family",
                "institution",
                "miss_category",
            ],
            "minimum_denominator_rule": "ALWAYS_REPORT_N_ALONGSIDE_RECALL; DO_NOT HIDE SMALL DENOMINATORS",
            "confidence_policy": "REPORT_EXACT_BINOMIAL_95_PERCENT_INTERVAL_WHEN_NUMERIC_RECALL_IS_COMPUTED",
            "precision_metric": "OUT_OF_SCOPE_FOR_STAGE_7_PRIMARY_OBJECTIVE",
        },
        "stage_boundaries": {
            "stage_7_2": "CONSTRUCT_AND_FREEZE_INDEPENDENT_REFERENCE_SET",
            "stage_7_3": "IMPLEMENT_MATCHING_AND_ATTRIBUTION",
            "stage_7_4": "COMPUTE_RECALL",
            "stage_7_5": "ANALYZE_FALSE_NEGATIVES",
            "stage_7_6": "CERTIFY_RECALL_MEASUREMENT",
            "source_changes_allowed_before_stage_8": False,
        },
    }
