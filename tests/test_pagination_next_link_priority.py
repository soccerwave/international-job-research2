import unittest

from src.sources.shared.pagination import next_listing_url


class NextListingUrlPriorityTests(unittest.TestCase):
    def test_prefers_same_path_pagination_over_misleading_job_detail(self):
        html = """
        <a href="/jobs/470367" title="Next">Misleading job detail</a>
        <a href="/jobs/search?page=1" rel="next">Next</a>
        """
        self.assertEqual(
            next_listing_url(html, "https://euraxess.ec.europa.eu/jobs/search"),
            "https://euraxess.ec.europa.eu/jobs/search?page=1",
        )

    def test_preserves_different_path_fallback_when_no_same_path_candidate_exists(self):
        html = '<a href="/next-page" rel="next">Next</a>'
        self.assertEqual(
            next_listing_url(html, "https://example.org/jobs"),
            "https://example.org/next-page",
        )


if __name__ == "__main__":
    unittest.main()
