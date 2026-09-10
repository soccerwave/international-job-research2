from __future__ import annotations

import contextlib
import io
import json
import unittest

from scripts.verify_stage7_2_reference_set import main
from src.runtime.reference_set import build_reference_construction_status


class Stage72ReferenceSetConstructionTests(unittest.TestCase):
    def test_roster_has_two_sources_per_core_market(self):
        status = build_reference_construction_status()
        self.assertEqual(status["reference_source_count"], 16)
        self.assertTrue(status["all_core_markets_have_two_sources"])
        self.assertEqual(set(status["country_source_counts"].values()), {2})

    def test_roster_has_no_duplicates(self):
        status = build_reference_construction_status()
        self.assertEqual(status["duplicate_source_id_count"], 0)
        self.assertEqual(status["duplicate_url_count"], 0)

    def test_window_is_active_and_not_frozen(self):
        status = build_reference_construction_status()
        self.assertEqual(status["status"], "ACTIVE_COLLECTION")
        self.assertTrue(status["source_roster_frozen"])
        self.assertFalse(status["reference_set_frozen"])
        self.assertEqual(status["window"]["start_date"], "2026-09-11")
        self.assertEqual(status["window"]["end_date"], "2026-09-24")
        self.assertEqual(status["window"]["capture_grace_end_date"], "2026-09-26")
        self.assertEqual(status["window"]["measurement_days"], 14)

    def test_acquisition_is_independent(self):
        status = build_reference_construction_status()
        policy = status["capture_policy"]
        self.assertFalse(policy["pipeline_output_allowed"])
        self.assertFalse(policy["pipeline_collector_code_allowed"])
        self.assertFalse(policy["comparison_with_pipeline_allowed_before_reference_freeze"])
        self.assertTrue(policy["reference_eligibility_must_be_frozen_before_matching"])

    def test_pre_match_schema_has_no_pipeline_fields(self):
        status = build_reference_construction_status()
        self.assertEqual(status["schema_forbidden_match_fields_present"], [])

    def test_relation_mix_contains_overlap_and_external_surfaces(self):
        status = build_reference_construction_status()
        self.assertGreater(status["relation_counts"].get("DIRECT_SOURCE_OVERLAP", 0), 0)
        self.assertGreater(status["relation_counts"].get("DIRECT_INSTITUTION_OVERLAP", 0), 0)
        self.assertGreater(status["relation_counts"].get("EXTERNAL_REFERENCE_SURFACE", 0), 0)
        self.assertEqual(status["relation_counts"].get("KNOWN_UNWIRED_REFERENCE_SURFACE"), 1)

    def test_verifier_passes_without_claiming_stage_done(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = main()
        payload = json.loads(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "PASS")
        self.assertFalse(payload["stage7_2_done"])
        self.assertEqual(payload["summary"]["reference_set_status"], "ACTIVE_COLLECTION")


if __name__ == "__main__":
    unittest.main()
