from __future__ import annotations

import contextlib
import io
import json
import unittest

from scripts.verify_stage7_1_recall_design import main
from src.runtime.recall_design import build_recall_measurement_design


class Stage71RecallMeasurementDesignTests(unittest.TestCase):
    def test_primary_metric_contract(self):
        design = build_recall_measurement_design()
        metric = design["primary_metric"]
        self.assertEqual(metric["name"], "END_TO_END_VACANCY_RECALL")
        self.assertEqual(metric["unit"], "UNIQUE_VACANCY")
        self.assertEqual(
            metric["formula"],
            "matched_unique_eligible_reference_vacancies / unique_eligible_reference_vacancies",
        )
        self.assertEqual(
            metric["duplicate_rule"],
            "SAME_VACANCY_COUNTS_ONCE_ACROSS_REFERENCE_SOURCES",
        )

    def test_reference_set_is_independent_and_frozen_before_matching(self):
        design = build_recall_measurement_design()
        rules = design["reference_set_rules"]
        self.assertIn("MUST_NOT_USE_PIPELINE_OUTPUT", rules["independence"])
        self.assertIn("MUST_BE_FROZEN_BEFORE_COMPARISON", rules["roster_freeze"])
        self.assertIn("ONLY_AFTER_REFERENCE_ELIGIBILITY_IS_FROZEN", rules["anti_leakage_rule"])

    def test_market_scope_uses_current_policy(self):
        design = build_recall_measurement_design()
        self.assertEqual(
            design["market_scope"]["primary_recall_markets"],
            ["NL", "DE", "IE", "GB", "BE", "FR", "AU", "AT"],
        )
        self.assertEqual(
            design["market_scope"]["opportunistic_markets"],
            ["IT", "PT", "CZ", "PL", "LU"],
        )

    def test_primary_role_scope_uses_frozen_primary_families(self):
        design = build_recall_measurement_design()
        self.assertEqual(
            design["role_scope"]["primary_denominator_families"],
            [
                "POSTDOC",
                "RESEARCH_FELLOW_POSTDOC",
                "ASSISTANT_PROFESSOR",
                "LECTURER",
                "RESEARCH_ASSISTANT_PROFESSOR",
                "TENURE_TRACK",
                "JUNIOR_PROFESSOR",
            ],
        )
        self.assertEqual(
            design["role_scope"]["secondary_treatment"],
            "REPORT_SEPARATELY_NOT_IN_PRIMARY_DENOMINATOR_UNLESS_POLICY_ENABLED",
        )

    def test_time_design_has_incident_and_stock_cohorts(self):
        design = build_recall_measurement_design()
        time_design = design["time_design"]
        self.assertEqual(time_design["mode"], "PROSPECTIVE_FIXED_WINDOW")
        self.assertEqual(time_design["measurement_days"], 14)
        self.assertEqual(time_design["pipeline_capture_grace_hours"], 48)
        self.assertEqual(time_design["primary_cohort"], "NEW_VACANCIES_POSTED_DURING_WINDOW")
        self.assertIn("REPORTED_SEPARATELY", time_design["active_stock_cohort"])
        self.assertIn("REPORTED_SEPARATELY", time_design["unknown_posted_date_cohort"])

    def test_no_source_change_is_authorized(self):
        design = build_recall_measurement_design()
        self.assertFalse(design["stage_boundaries"]["source_changes_allowed_before_stage_8"])

    def test_verifier_passes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = main()
        payload = json.loads(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(all(payload["checks"].values()))
        self.assertEqual(payload["behavior"], "READ_ONLY_DESIGN_VERIFICATION")


if __name__ == "__main__":
    unittest.main()
