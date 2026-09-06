import os
import unittest
from collections import Counter
from unittest.mock import patch

from src.runtime.live_shards import LINKEDIN_EUROPE_PARTITIONS, LINKEDIN_EUROPE_QUERIES
from src.runtime.production_shards import PRODUCTION_SHARD_IDS
from src.runtime.production_sources import production_source_map


EXPECTED_COUNTRIES = {
    "Netherlands", "Germany", "Ireland", "United Kingdom", "Belgium", "France", "Austria",
    "Italy", "Portugal", "Czechia", "Poland", "Luxembourg",
}
EXPECTED_PARTITIONS = {
    "linkedin-europe-germany",
    "linkedin-europe-west",
    "linkedin-europe-france-austria",
    "linkedin-europe-opportunistic",
}


class LinkedInRuntimeArchitectureTests(unittest.TestCase):
    def test_partition_union_is_exact_and_non_overlapping(self):
        self.assertEqual(set(LINKEDIN_EUROPE_PARTITIONS), EXPECTED_PARTITIONS)
        flattened = [country for countries in LINKEDIN_EUROPE_PARTITIONS.values() for country in countries]
        self.assertEqual(set(flattened), EXPECTED_COUNTRIES)
        self.assertEqual(len(flattened), len(EXPECTED_COUNTRIES))
        self.assertEqual(Counter(flattened), Counter(EXPECTED_COUNTRIES))
        self.assertEqual(LINKEDIN_EUROPE_PARTITIONS["linkedin-europe-germany"], ("Germany",))

    def test_production_topology_matches_expected_shards(self):
        production = production_source_map()
        self.assertEqual(set(PRODUCTION_SHARD_IDS), set(production))
        self.assertNotIn("linkedin-europe", production)
        self.assertTrue(EXPECTED_PARTITIONS.issubset(production))

    def test_partitions_remain_one_logical_source(self):
        production = production_source_map()
        calls = [production[shard][0] for shard in EXPECTED_PARTITIONS]
        self.assertEqual({call.source_id for call in calls}, {"linkedin_europe"})
        self.assertEqual({call.report_key for call in calls}, {"linkedin_mads"})

    def test_each_partition_preserves_queries_age_and_uncapped_pagination(self):
        captured = []

        def fake_collect(**kwargs):
            captured.append(kwargs)
            return []

        with patch.dict(os.environ, {"AI_JOB_SEARCH_MADS_REPO": "/tmp/mads"}, clear=False), patch(
            "src.runtime.production_sources.linkedin_mads.collect", side_effect=fake_collect
        ):
            production = production_source_map(limit=None)
            for shard in LINKEDIN_EUROPE_PARTITIONS:
                production[shard][0].collector()

        self.assertEqual(len(captured), len(LINKEDIN_EUROPE_PARTITIONS))
        by_locations = {tuple(row["locations"]): row for row in captured}
        self.assertEqual(set(by_locations), set(LINKEDIN_EUROPE_PARTITIONS.values()))
        for row in captured:
            self.assertEqual(tuple(row["queries"]), LINKEDIN_EUROPE_QUERIES)
            self.assertIsNone(row["limit_per_search"])
            self.assertEqual(row["jobage_days"], 14)
            self.assertIsNone(row["max_jobs"])
            self.assertTrue(row["enrich_detail"])


if __name__ == "__main__":
    unittest.main()
