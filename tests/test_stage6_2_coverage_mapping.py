from __future__ import annotations

import contextlib
import io
import json
import unittest

from scripts.verify_stage6_2_coverage_mapping import main
from src.runtime.coverage_mapping import build_coverage_mapping


class Stage62CoverageMappingTests(unittest.TestCase):
    def test_summary_matches_current_configured_mapping(self):
        mapping = build_coverage_mapping()
        self.assertEqual(mapping["country_count"], 13)
        self.assertEqual(mapping["country_execution_link_count"], 58)
        self.assertEqual(len(mapping["board_family_rows"]), 17)
        self.assertEqual(len(mapping["institution_rows"]), 18)
        self.assertEqual(mapping["unresolved_geography_execution_count"], 5)

    def test_overlap_distribution_is_deterministic(self):
        mapping = build_coverage_mapping()
        self.assertEqual(
            mapping["country_board_family_overlap_counts"],
            {"3": 7, "4": 4, "5": 2},
        )
        self.assertTrue(mapping["all_explicit_countries_have_multi_board_overlap"])

    def test_country_mapping_examples(self):
        mapping = build_coverage_mapping()
        self.assertEqual(mapping["country_rows"]["AU"]["execution_count"], 9)
        self.assertEqual(mapping["country_rows"]["AU"]["board_family_count"], 4)
        self.assertEqual(mapping["country_rows"]["IE"]["execution_count"], 9)
        self.assertEqual(mapping["country_rows"]["IE"]["board_family_count"], 5)
        self.assertEqual(mapping["country_rows"]["AT"]["board_family_count"], 5)
        self.assertEqual(mapping["country_rows"]["FR"]["board_family_count"], 4)

    def test_unresolved_geography_sources_are_preserved_not_invented(self):
        mapping = build_coverage_mapping()
        unresolved = {row["source_id"] for row in mapping["unresolved_geography_executions"]}
        self.assertEqual(unresolved, {"jobs_ac_uk", "academics_de", "ecss", "dvs", "fens"})

    def test_institution_country_mapping_is_traceable(self):
        mapping = build_coverage_mapping()
        self.assertEqual(
            mapping["institution_rows"]["University College Dublin"]["configured_country_codes"],
            ["IE"],
        )
        self.assertEqual(
            mapping["institution_rows"]["Monash University"]["configured_country_codes"],
            ["AU"],
        )
        self.assertEqual(
            mapping["institution_rows"]["University of Vienna"]["configured_country_codes"],
            ["AT"],
        )

    def test_board_family_mapping_is_traceable(self):
        mapping = build_coverage_mapping()
        self.assertEqual(
            mapping["board_family_rows"]["LinkedIn"]["configured_country_codes"],
            ["AT", "AU", "BE", "CZ", "DE", "FR", "GB", "IE", "IT", "LU", "NL", "PL", "PT"],
        )
        self.assertEqual(
            mapping["board_family_rows"]["CoreHR"]["configured_country_codes"],
            ["IE"],
        )

    def test_verifier_passes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = main()
        result = json.loads(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["behavior"], "READ_ONLY_MAPPING")


if __name__ == "__main__":
    unittest.main()
