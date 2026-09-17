import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
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
  <select name="job_country[]">
    <option value="798">Netherlands</option>
    <option value="794">Germany</option>
  </select>
  <select name="offer_type[]"><option value="job_offer">Job Offer</option></select>
</form>
'''


class EuraxessStage41Tests(unittest.TestCase):
    def test_uses_stable_get_facets_and_preserves_them_on_next_link(self):
        page1 = FILTER_FORM + (
            '<article>Germany <a href="/jobs/100">Research Fellow A</a></article>'
            '<a rel="next" href="/jobs/search?page=1">Next</a>'
        )
        page2 = FILTER_FORM + '<article>Germany <a href="/jobs/101">Research Fellow B</a></article>'
        gets = []

        def get(url, **kwargs):
            params = kwargs.get("params")
            gets.append((url, params))
            if len(gets) == 1:
                return Response(FILTER_FORM)
            if len(gets) == 2:
                self.assertEqual(
                    params,
                    [("f[0]", "job_country:794"), ("f[1]", "offer_type:job_offer")],
                )
                return Response(
                    page1,
                    "https://euraxess.ec.europa.eu/jobs/search?f%5B0%5D=job_country%3A794&f%5B1%5D=offer_type%3Ajob_offer",
                )
            query = parse_qs(urlsplit(url).query)
            self.assertEqual(query["page"], ["1"])
            self.assertEqual(query["f[0]"], ["job_country:794"])
            self.assertEqual(query["f[1]"], ["offer_type:job_offer"])
            return Response(page2, url)

        def post(*args, **kwargs):
            raise AssertionError("EURAXESS collector must not POST the exposed filter form")

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
        self.assertEqual([row["source"]["raw_extra"]["filter_transport"] for row in rows], ["GET_FACET", "GET_FACET"])
        self.assertEqual(coverage[-1]["stop_reason"], "last_page")
        self.assertTrue(coverage[-1]["complete"])

    def test_distinct_country_facets_do_not_silently_reuse_global_results(self):
        gets = []

        def get(url, **kwargs):
            params = kwargs.get("params")
            gets.append((url, params))
            if len(gets) == 1:
                return Response(FILTER_FORM)
            facet = dict(params or []).get("f[0]")
            if facet == "job_country:798":
                return Response(
                    FILTER_FORM + '<article>Netherlands <a href="/jobs/200">Dutch Research Fellow</a></article>',
                    "https://euraxess.ec.europa.eu/jobs/search?f%5B0%5D=job_country%3A798&f%5B1%5D=offer_type%3Ajob_offer",
                )
            if facet == "job_country:794":
                return Response(
                    FILTER_FORM + '<article>Germany <a href="/jobs/300">German Research Fellow</a></article>',
                    "https://euraxess.ec.europa.eu/jobs/search?f%5B0%5D=job_country%3A794&f%5B1%5D=offer_type%3Ajob_offer",
                )
            raise AssertionError(f"Unexpected facet request: {params}")

        with capture_coverage():
            rows = euraxess.collect(
                country_codes=("NL", "DE"),
                pages_per_country=None,
                max_jobs=None,
                enrich_detail=False,
                session=SimpleNamespace(get=get, post=lambda *a, **k: None),
                pace_seconds=0,
            )

        self.assertEqual([row["source"]["source_job_id"] for row in rows], ["200", "300"])
        self.assertEqual([row["location"]["country_code"] for row in rows], ["NL", "DE"])
        self.assertEqual(
            [row["source"]["raw_extra"]["country_facet"] for row in rows],
            ["job_country:798", "job_country:794"],
        )

    def test_429_retry_honors_retry_after_for_get(self):
        responses = [
            Response(status_code=429, headers={"Retry-After": "2"}),
            Response(text="ok", status_code=200),
        ]
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            return responses.pop(0)

        with patch.object(euraxess.time, "sleep") as sleep:
            response = euraxess._request(
                SimpleNamespace(post=lambda *a, **k: None, get=get),
                "GET",
                euraxess.SEARCH_URL,
                params=[("f[0]", "job_country:794"), ("f[1]", "offer_type:job_offer")],
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
