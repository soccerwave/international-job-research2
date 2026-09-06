import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.sources.shared import euraxess
from src.sources.shared.pagination import capture_coverage


class Response:
    def __init__(self, text="", url="https://euraxess.ec.europa.eu/jobs/search", status_code=200, headers=None):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


FILTER_FORM = '''
<form method="post" action="/jobs/search">
  <input type="hidden" name="form_build_id" value="build-1">
  <input type="hidden" name="form_id" value="views_exposed_form">
  <select name="job_country[]"><option value="794">Germany</option></select>
  <select name="offer_type[]"><option value="job_offer">Job Offer</option></select>
  <button type="submit" name="op" value="Apply filters">Apply filters</button>
  <button type="submit" name="op" value="Clear filters">Clear filters</button>
</form>
'''


class EuraxessStage41Tests(unittest.TestCase):
    def test_posts_live_filter_form_then_follows_site_next_link(self):
        page1 = FILTER_FORM + (
            '<article>Germany <a href="/jobs/100">Research Fellow A</a></article>'
            '<a rel="next" href="/jobs/search?page=1">Next</a>'
        )
        page2 = FILTER_FORM + '<article>Germany <a href="/jobs/101">Research Fellow B</a></article>'
        gets = []
        posts = []

        def get(url, **kwargs):
            gets.append((url, kwargs.get("params")))
            if len(gets) == 1:
                return Response(FILTER_FORM)
            return Response(page2, "https://euraxess.ec.europa.eu/jobs/search?page=1")

        def post(url, **kwargs):
            posts.append((url, kwargs.get("data")))
            return Response(page1, "https://euraxess.ec.europa.eu/jobs/search?f%5B0%5D=job_country%3A794")

        with capture_coverage() as coverage:
            rows = euraxess.collect(
                country_codes=("DE",),
                pages_per_country=None,
                max_jobs=None,
                enrich_detail=False,
                session=SimpleNamespace(get=get, post=post),
                pace_seconds=0,
            )

        self.assertEqual([row["source"]["source_job_id"] for row in rows], ["100", "101"])
        self.assertEqual(len(posts), 1)
        payload = dict(posts[0][1])
        self.assertEqual(payload["form_build_id"], "build-1")
        self.assertEqual(payload["form_id"], "views_exposed_form")
        self.assertEqual(payload["job_country[]"], "794")
        self.assertEqual(payload["offer_type[]"], "job_offer")
        self.assertEqual(payload["op"], "Apply filters")
        self.assertEqual(gets[1], ("https://euraxess.ec.europa.eu/jobs/search?page=1", None))
        self.assertEqual(coverage[-1]["stop_reason"], "last_page")
        self.assertTrue(coverage[-1]["complete"])

    def test_429_retry_honors_retry_after_for_post(self):
        responses = [
            Response(status_code=429, headers={"Retry-After": "2"}),
            Response(text="ok", status_code=200),
        ]
        calls = []

        def post(url, **kwargs):
            calls.append(url)
            return responses.pop(0)

        with patch.object(euraxess.time, "sleep") as sleep:
            response = euraxess._request(
                SimpleNamespace(post=post, get=lambda *a, **k: None),
                "POST",
                euraxess.SEARCH_URL,
                data=[("job_country[]", "794")],
                attempts=3,
                pace_seconds=0,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once_with(2.0)

    def test_czechia_accepts_current_or_legacy_country_label(self):
        facets = {"czech republic": "job_country:203"}
        self.assertEqual(euraxess._facet_for_code(facets, "CZ"), "job_country:203")
        facets = {"czechia": "job_country:203"}
        self.assertEqual(euraxess._facet_for_code(facets, "CZ"), "job_country:203")


if __name__ == "__main__":
    unittest.main()
