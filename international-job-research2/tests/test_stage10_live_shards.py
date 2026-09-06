from __future__ import annotations

import unittest

from src.runtime.live_shards import LINKEDIN_EUROPE_PARTITIONS, _specs


class Stage10LiveShardContractTests(unittest.TestCase):
    def test_linkedin_diagnostic_report_key_matches_emitted_source_key(self):
        specs = _specs()
        for shard_id in LINKEDIN_EUROPE_PARTITIONS:
            self.assertEqual(specs[shard_id][0].source_id, "linkedin_europe")
            self.assertEqual(specs[shard_id][0].report_key, "linkedin_mads")
        self.assertEqual(specs["linkedin-australia"][0].report_key, "linkedin_mads")


if __name__ == "__main__":
    unittest.main()
