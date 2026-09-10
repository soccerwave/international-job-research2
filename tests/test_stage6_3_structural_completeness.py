from __future__ import annotations

import contextlib
import io
import json
import unittest

from scripts.verify_stage6_3_structural_completeness import main
from src.runtime.structural_completeness import build_structural_completeness_checks


class Stage63StructuralCompletenessTests(unittest.TestCase):
    def test_current_structural_summary(self):
        audit = build_structural_completeness_checks()
        self.assertEqual(audit["target_countries_without_explicit_wiring"], [])
        self.assertEqual(audit["tenant_registry_count"], 17)
        self.assertEqual(audit["unwired_registered_tenant_count"], 0)
        self.assertEqual(audit["linkedin_partition_count"], 4)
        self.assertEqual(audit["unwired_linkedin_partition_count"], 0)
        self.assertEqual(audit["portal_collector_surface_count"], 6)
        self.assertEqual(audit["unresolved_geography_execution_count"], 5)
        self.assertEqual(audit["shared_report_key_count"], 1)
        self.assertEqual(audit["review_finding_count"], 6)
        self.assertEqual(audit["info_finding_count"], 3)
        self.assertEqual(audit["status"], "STRUCTURAL_FINDINGS_PRESENT")

    def test_uniroles_is_the_only_unwired_portal_source_id(self):
        audit = build_structural_completeness_checks()
        rows = [
            row for row in audit["findings"]
            if row["code"] == "UNWIRED_EXISTING_COLLECTOR"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_id"], "uniroles_au")
        self.assertEqual(rows[0]["collectors"], ["collect_uniroles"])

    def test_legacy_alternate_implementations_are_not_marked_unwired(self):
        audit = build_structural_completeness_checks()
        rows = {
            row["source_id"]
            for row in audit["findings"]
            if row["code"] == "ALTERNATE_COLLECTOR_IMPLEMENTATION"
        }
        self.assertEqual(rows, {"cnrs_emploi", "university_vacancies_ie"})

    def test_unresolved_geography_sources_are_review_findings(self):
        audit = build_structural_completeness_checks()
        rows = {
            row["source_id"]
            for row in audit["findings"]
            if row["code"] == "UNRESOLVED_CONFIGURED_GEOGRAPHY"
        }
        self.assertEqual(rows, {"jobs_ac_uk", "academics_de", "ecss", "dvs", "fens"})

    def test_shared_report_key_is_linkedin_only(self):
        audit = build_structural_completeness_checks()
        self.assertEqual(
            audit["shared_report_keys"],
            [{"report_key": "linkedin_mads", "source_ids": ["linkedin_australia", "linkedin_europe"]}],
        )

    def test_no_registered_tenant_or_linkedin_partition_is_dormant(self):
        audit = build_structural_completeness_checks()
        self.assertTrue(all(row["wired"] for row in audit["tenant_rows"]))
        self.assertTrue(all(row["wired"] for row in audit["linkedin_partition_rows"]))

    def test_verifier_passes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = main()
        result = json.loads(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["behavior"], "READ_ONLY_STRUCTURAL_AUDIT")


if __name__ == "__main__":
    unittest.main()
