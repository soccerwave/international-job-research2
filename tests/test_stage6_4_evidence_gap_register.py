from __future__ import annotations

import contextlib
import io
import json
import unittest

from scripts.verify_stage6_4_gap_register import main
from src.runtime.gap_register import build_evidence_gap_register


class Stage64EvidenceGapRegisterTests(unittest.TestCase):
    def test_register_classification_counts(self):
        register = build_evidence_gap_register()
        self.assertEqual(register["entry_count"], 9)
        self.assertEqual(
            register["classification_counts"],
            {
                "CONFIRMED_STRUCTURAL_GAP": 1,
                "NOT_GAP": 3,
                "NOT_STRUCTURAL_GAP_RECALL_PENDING": 5,
            },
        )

    def test_uniroles_is_only_confirmed_structural_gap(self):
        register = build_evidence_gap_register()
        self.assertEqual(register["confirmed_structural_gap_ids"], ["uniroles_au"])
        entry = next(
            row for row in register["entries"]
            if row["identifier"] == "uniroles_au"
        )
        self.assertEqual(entry["disposition"], "REGISTER_ONLY_DEFER_SOURCE_CHANGE_UNTIL_POST_RECALL_GAP_ANALYSIS")

    def test_unresolved_geography_is_not_promoted_to_gap(self):
        register = build_evidence_gap_register()
        self.assertEqual(
            set(register["recall_pending_ids"]),
            {"jobs_ac_uk", "academics_de", "ecss", "dvs", "fens"},
        )

    def test_informational_findings_are_not_gaps(self):
        register = build_evidence_gap_register()
        self.assertEqual(
            set(register["not_gap_ids"]),
            {"cnrs_emploi", "university_vacancies_ie", "linkedin_mads"},
        )

    def test_source_change_is_explicitly_forbidden(self):
        register = build_evidence_gap_register()
        self.assertFalse(register["source_change_allowed"])
        self.assertEqual(
            register["next_decision_boundary"],
            "AFTER_STAGE_7_RECALL_AND_STAGE_8_GAP_ANALYSIS",
        )

    def test_every_entry_retains_structural_finding_and_evidence(self):
        register = build_evidence_gap_register()
        for entry in register["entries"]:
            self.assertTrue(entry["structural_finding"])
            self.assertTrue(entry["evidence"])
            self.assertTrue(entry["disposition"])

    def test_verifier_passes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = main()
        result = json.loads(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["behavior"], "READ_ONLY_REGISTER")


if __name__ == "__main__":
    unittest.main()
