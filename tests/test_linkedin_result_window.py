import unittest

from src.sources.shared.pagination import capture_coverage, paginate


class LinkedInResultWindowTests(unittest.TestCase):
    def test_linkedin_page_101_http_400_is_known_window_ceiling(self):
        def fetch(page):
            if page == 101:
                raise RuntimeError('{"error":"HTTP 400","code":"SEARCH_FAILED"}')
            return ([{"id": str(page)}], None, None)

        with capture_coverage() as audit:
            rows = paginate(
                fetch,
                source="linkedin_mads:United Kingdom:research fellow",
                start=1,
            )

        self.assertEqual(len(rows), 100)
        self.assertEqual(audit[-1]["stop_reason"], "known_result_window_limit")
        self.assertTrue(audit[-1]["complete"])
        self.assertIsNone(audit[-1]["error"])

    def test_linkedin_earlier_http_400_remains_incomplete_failure(self):
        def fetch(page):
            if page == 51:
                raise RuntimeError('{"error":"HTTP 400","code":"SEARCH_FAILED"}')
            return ([{"id": str(page)}], None, None)

        with capture_coverage() as audit:
            rows = paginate(
                fetch,
                source="linkedin_mads:Germany:lecturer",
                start=1,
            )

        self.assertEqual(len(rows), 50)
        self.assertEqual(audit[-1]["stop_reason"], "request_failed")
        self.assertFalse(audit[-1]["complete"])

    def test_non_linkedin_page_101_http_400_remains_failure(self):
        def fetch(page):
            if page == 101:
                raise RuntimeError('{"error":"HTTP 400","code":"SEARCH_FAILED"}')
            return ([{"id": str(page)}], None, None)

        with capture_coverage() as audit:
            rows = paginate(fetch, source="other_source", start=1)

        self.assertEqual(len(rows), 100)
        self.assertEqual(audit[-1]["stop_reason"], "request_failed")
        self.assertFalse(audit[-1]["complete"])


if __name__ == "__main__":
    unittest.main()
