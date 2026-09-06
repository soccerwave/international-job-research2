from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.runtime import live_shards
from src.runtime.production_sources import production_source_map


class Stage414QueryTaxonomyTests(unittest.TestCase):
    def test_europe_taxonomy_adds_only_evidence_supported_role_queries(self):
        self.assertEqual(
            live_shards.LINKEDIN_EUROPE_QUERIES,
            (
                "postdoctoral researcher",
                "research fellow",
                "assistant professor",
                "lecturer",
                "research associate",
                "postdoctoral fellow",
            ),
        )
        self.assertNotIn("researcher", live_shards.LINKEDIN_EUROPE_QUERIES)
        self.assertNotIn("research assistant", live_shards.LINKEDIN_EUROPE_QUERIES)
        self.assertNotIn("research scientist", live_shards.LINKEDIN_EUROPE_QUERIES)

    def test_australia_taxonomy_adds_research_associate_and_postdoctoral_fellow(self):
        self.assertEqual(
            live_shards.LINKEDIN_AUSTRALIA_QUERIES,
            (
                "postdoctoral researcher",
                "research fellow",
                "lecturer",
                "research associate",
                "postdoctoral fellow",
            ),
        )

    def test_jobs_ac_uk_taxonomy_adds_three_board_appropriate_queries(self):
        self.assertEqual(
            live_shards.JOBS_AC_UK_QUERIES,
            (
                "postdoctoral",
                "research fellow",
                "lecturer",
                "exercise",
                "neuroscience",
                "research associate",
                "postdoctoral fellow",
                "research scientist",
            ),
        )
        self.assertNotIn("researcher", live_shards.JOBS_AC_UK_QUERIES)
        self.assertNotIn("research assistant", live_shards.JOBS_AC_UK_QUERIES)

    def test_production_wiring_uses_central_taxonomies(self):
        old = os.environ.get("AI_JOB_SEARCH_MADS_REPO")
        os.environ["AI_JOB_SEARCH_MADS_REPO"] = "/tmp/mads"
        try:
            with patch("src.runtime.production_sources.linkedin_mads.collect", return_value=[]) as linkedin_collect, \
                 patch("src.runtime.production_sources.jobs_ac_uk.collect", return_value=[]) as jobs_collect:
                specs = production_source_map(limit=1)
                specs["linkedin-europe-germany"][0].collector()
                self.assertEqual(linkedin_collect.call_args.kwargs["queries"], live_shards.LINKEDIN_EUROPE_QUERIES)
                self.assertIsNone(linkedin_collect.call_args.kwargs["limit_per_search"])

                linkedin_collect.reset_mock()
                specs["linkedin-australia"][0].collector()
                self.assertEqual(linkedin_collect.call_args.kwargs["queries"], live_shards.LINKEDIN_AUSTRALIA_QUERIES)
                self.assertIsNone(linkedin_collect.call_args.kwargs["limit_per_search"])

                specs["uk-ireland-portals"][0].collector()
                self.assertEqual(jobs_collect.call_args.kwargs["keywords"], live_shards.JOBS_AC_UK_QUERIES)
                self.assertIsNone(jobs_collect.call_args.kwargs["pages_per_query"])
        finally:
            if old is None:
                os.environ.pop("AI_JOB_SEARCH_MADS_REPO", None)
            else:
                os.environ["AI_JOB_SEARCH_MADS_REPO"] = old

    def test_shadow_wiring_uses_same_taxonomies(self):
        old = os.environ.get("AI_JOB_SEARCH_MADS_REPO")
        os.environ["AI_JOB_SEARCH_MADS_REPO"] = "/tmp/mads"
        try:
            with patch("src.runtime.live_shards.linkedin_mads.collect", return_value=[]) as linkedin_collect, \
                 patch("src.runtime.live_shards.jobs_ac_uk.collect", return_value=[]) as jobs_collect:
                specs = live_shards._specs()
                specs["linkedin-europe-germany"][0].collector()
                self.assertEqual(linkedin_collect.call_args.kwargs["queries"], live_shards.LINKEDIN_EUROPE_QUERIES)

                linkedin_collect.reset_mock()
                specs["linkedin-australia"][0].collector()
                self.assertEqual(linkedin_collect.call_args.kwargs["queries"], live_shards.LINKEDIN_AUSTRALIA_QUERIES)

                specs["uk-ireland-portals"][0].collector()
                self.assertEqual(jobs_collect.call_args.kwargs["keywords"], live_shards.JOBS_AC_UK_QUERIES)
        finally:
            if old is None:
                os.environ.pop("AI_JOB_SEARCH_MADS_REPO", None)
            else:
                os.environ["AI_JOB_SEARCH_MADS_REPO"] = old


if __name__ == "__main__":
    unittest.main()
