from __future__ import annotations

import unittest
from src.llm.production_shadow import ProductionShadowInputs
from src.llm.source_exclusions import exclude_paid_luna_sources, is_excluded_from_paid_luna


def job(job_id, link, source_id="", title="Research Analyst"):
    return {"canonical_id": job_id, "source": {
        "listing_url": link, "source_id": source_id},
        "position": {"title_raw": title}}


class PaidLunaExclusionsTests(unittest.TestCase):
    def test_only_exact_alignerr_source_and_subdomains_excluded(self):
        self.assertTrue(is_excluded_from_paid_luna(job("a", "https://www.alignerr.com/jobs/test")))
        self.assertTrue(is_excluded_from_paid_luna(job("b", "https://jobs.alignerr.com/posting")))
        self.assertTrue(is_excluded_from_paid_luna(job("c", "https://example.org", "alignerr")))
        self.assertFalse(is_excluded_from_paid_luna(job("d", "https://notalignerr.com/jobs")))
        self.assertFalse(is_excluded_from_paid_luna(job("e", "https://example.org/alignerr.com")))
        self.assertFalse(is_excluded_from_paid_luna(job("f", "https://example.org", "other", "Alignerr Research Analyst")))

    def test_aggregator_link_exact_alignerr_employer_excluded(self):
        job = {
            "canonical_id": "via-linkedin",
            "source": {"listing_url": "https://www.linkedin.com/jobs/view/12345",
                       "source_id": "linkedin-europe-uk"},
            "position": {"title_raw": "General Postdoctoral Researcher",
                         "institution_raw": "Alignerr"},
        }
        self.assertTrue(is_excluded_from_paid_luna(job))
        job["position"]["institution_raw"] = "Alignerr Research Partners"
        self.assertFalse(is_excluded_from_paid_luna(job))
        job["position"]["institution_raw"] = "University of Barcelona"
        self.assertFalse(is_excluded_from_paid_luna(job))

    def test_excluded_before_both_paid_paths_and_keeps_unrelated(self):
        inputs = ProductionShadowInputs(
            jobs=(job("a","https://alignerr.com/a"), job("b","https://example.org/b"),
                  job("c","https://jobs.alignerr.com/c"), job("d","https://example.org/d")),
            main_job_ids=("a","b"), rescue_candidate_job_ids=("c","d"))
        result = exclude_paid_luna_sources(inputs)
        self.assertEqual(result.excluded_job_ids, ("a","c"))
        self.assertEqual(result.inputs.main_job_ids, ("b",))
        self.assertEqual(result.inputs.rescue_candidate_job_ids, ("d",))
        self.assertEqual(tuple(j["canonical_id"] for j in result.inputs.jobs), ("b","d"))
        self.assertEqual(len(inputs.jobs), 4)


if __name__ == "__main__":
    unittest.main()
