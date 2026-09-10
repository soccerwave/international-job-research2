from __future__ import annotations

import contextlib
import io
import json
import unittest

from scripts.verify_stage6_1_board_inventory import main
from src.runtime.board_inventory import build_current_board_inventory


class Stage61CurrentBoardInventoryTests(unittest.TestCase):
    def test_inventory_summary_matches_current_wiring(self):
        inventory = build_current_board_inventory()
        self.assertEqual(inventory["production_shard_count"], 17)
        self.assertEqual(inventory["source_execution_count"], 33)
        self.assertEqual(inventory["unique_source_id_count"], 30)
        self.assertEqual(inventory["unique_report_key_count"], 29)
        self.assertEqual(inventory["board_family_count"], 17)
        self.assertEqual(inventory["institution_specific_source_count"], 18)
        self.assertEqual(inventory["institution_count"], 18)
        self.assertEqual(inventory["configured_country_count"], 13)

    def test_configured_countries_are_explicit_current_targets(self):
        inventory = build_current_board_inventory()
        self.assertEqual(
            inventory["configured_country_codes"],
            ["AT", "AU", "BE", "CZ", "DE", "FR", "GB", "IE", "IT", "LU", "NL", "PL", "PT"],
        )

    def test_board_kind_counts_cover_every_execution(self):
        inventory = build_current_board_inventory()
        self.assertEqual(
            inventory["board_kind_counts"],
            {
                "ACADEMIC_JOB_BOARD": 2,
                "INSTITUTION_ATS": 17,
                "INSTITUTION_DIRECT": 1,
                "MULTI_COUNTRY_AGGREGATOR": 2,
                "NATIONAL_ACADEMIC_PORTAL": 2,
                "RESEARCH_ORGANISATION_PORTAL": 1,
                "SEARCH_PLATFORM": 5,
                "THEMATIC_JOB_BOARD": 3,
            },
        )
        self.assertEqual(sum(inventory["board_kind_counts"].values()), inventory["source_execution_count"])

    def test_geography_modes_cover_every_execution(self):
        inventory = build_current_board_inventory()
        self.assertEqual(
            inventory["geography_mode_counts"],
            {
                "BOARD_NATIVE_UNFILTERED": 1,
                "EXPLICIT_COUNTRY_FILTER": 2,
                "EXPLICIT_LOCATION_SEARCH": 5,
                "FIXED_SOURCE_COUNTRY": 21,
                "LISTING_INFERRED_COUNTRY": 1,
                "LISTING_NATIVE": 3,
            },
        )

    def test_institution_inventory_contains_current_tenants(self):
        inventory = build_current_board_inventory()
        expected = {
            "Deakin University",
            "Dublin City University",
            "Flinders University",
            "Ghent University",
            "Griffith University",
            "Monash University",
            "The University of Queensland",
            "The University of Sydney",
            "Trinity College Dublin",
            "UCLouvain",
            "UNSW Sydney",
            "University College Cork",
            "University College Dublin",
            "University of Galway",
            "University of Innsbruck",
            "University of Vienna",
            "Vrije Universiteit Brussel",
            "Western Sydney University",
        }
        self.assertEqual(set(inventory["institutions"]), expected)

    def test_linkedin_europe_is_inventory_by_partition(self):
        inventory = build_current_board_inventory()
        rows = [
            row for row in inventory["executions"]
            if row["source_id"] == "linkedin_europe"
        ]
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            {row["shard_id"] for row in rows},
            {
                "linkedin-europe-germany",
                "linkedin-europe-west",
                "linkedin-europe-france-austria",
                "linkedin-europe-opportunistic",
            },
        )

    def test_verifier_passes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = main()
        result = json.loads(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["behavior"], "READ_ONLY_INVENTORY")


if __name__ == "__main__":
    unittest.main()
