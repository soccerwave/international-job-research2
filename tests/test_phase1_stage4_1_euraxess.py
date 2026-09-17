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


FILTER_FORM = """
<form method="post" action="/jobs/search">
  <select name="job_country[]">
    <option value="794">Germany</option>
    <option value="798">Netherlands</option>
  </select>
  <select name="offer_type[]"><option value="job_offer">Job Offer</option></select>
  <button type="submit" name="op" value="Apply filters">Apply filters</button>
</form>
"""


def filtered_url(country_facet, page=None):
    suffix = (
        f"?f%5B0%5D={country_facet.replace(':', '%3A')}"
        "&f%5B1%5D=offer_type%3Ajob_offer"
    )
    if page is not None:
        suffix += f"&page={page}"
    return euraxess.SEARCH_URL + suffix


class EuraxessStage41Tests(unittest.TestCase):
    def test_discovers_current_get_facets_dynamically(self):
        facets = euraxess.discover_country_facets(FILTER_FORM)
        self.assertEqual(facets["germany"], "job_country:794")
        self.assertEqual(facets["netherlands"], "job_country:798")
        self.assertEqual(euraxess.discover_offer_type_facet(FILTER_FORM), "offer_type:job_offer")

    def test_uses_get_facets_and_follows_filtered_next_link_unchanged(self):
        next_href = "?f%5B0%5D=job_country%3A794&f%5B1%5D=offer_type%3Ajob_offer&page=1"
        page1 = FILTER_FORM + (
            '<article>Germany <a href="/jobs/100">Research Fellow A</a></article>'
            f'<a rel="next" href="{next_href}">Next</a>'
        )
        page2 = FILTER_FORM + '<article>Germany <a href="/jobs/101">Research Fellow B</a></article>'
        gets = []

        def get(url, **kwargs):
            gets.append((url, kwargs.get("params")))
            if len(gets) == 1:
                return Response(FILTER_FORM)
            if len(gets) == 2:
                return Response(page1, filtered_url("job_country:794"))
            return Response(page2, filtered_url("job_country:794", page=1))

        with capture_coverage() as coverage:
            rows = euraxess.collect(
                country_codes=("DE",),
                pages_per_country=None,
                max_jobs=None,
                enrich_detail=False,
                session=SimpleNamespace(get=get),
                pace_seconds=0,
            )

        self.assertEqual([row["source"]["source_job_id"] for row in rows], ["100", "101"])
        self.assertEqual(
            gets[1],
            (
                euraxess.SEARCH_URL,
                [("f[0]", "job_country:794"), ("f[1]", "offer_type:job_offer")],
            ),
        )
        self.assertEqual(gets[2], (euraxess.SEARCH_URL + next_href, None))
        self.assertEqual(rows[0]["raw_extra"]["filter_transport"], "GET_FACET")
        self.assertEqual(coverage[-1]["stop_reason"], "last_page")
        self.assertTrue(coverage[-1]["complete"])

    def test_pagination_that_drops_facets_is_partial_not_healthy(self):
        page1 = FILTER_FORM + (
            '<article>Germany <a href="/jobs/100">Research Fellow A</a></article>'
            '<a rel="next" href="/jobs/search?page=1">Next</a>'
        )
        gets = []

        def get(url, **kwargs):
            gets.append((url, kwargs.get("params")))
            if len(gets) == 1:
                return Response(FILTER_FORM)
            return Response(page1, filtered_url("job_country:794"))

        with capture_coverage() as coverage:
            rows = euraxess.collect(
                country_codes=("DE",),
                pages_per_country=None,
                max_jobs=None,
                enrich_detail=False,
                session=SimpleNamespace(get=get),
                pace_seconds=0,
            )

        self.assertEqual([row["source"]["source_job_id"] for row in rows], ["100"])
        self.assertEqual(coverage[-1]["stop_reason"], "request_failed")
        self.assertFalse(coverage[-1]["complete"])
        self.assertIn("lost active facets", coverage[-1]["error"])

    def test_identical_country_result_sets_are_flagged_and_country_becomes_untrusted(self):
        same_page = (
            '<article><span>Global</span><a href="/jobs/100">Research Fellow A</a></article>'
            '<article><span>Global</span><a href="/jobs/101">Research Fellow B</a></article>'
        )
        gets = []

        def get(url, **kwargs):
            gets.append((url, kwargs.get("params")))
            if len(gets) == 1:
                return Response(FILTER_FORM)
            params = dict(kwargs.get("params") or [])
            return Response(same_page, filtered_url(params["f[0]"]))

        with capture_coverage() as coverage:
            rows = euraxess.collect(
                country_codes=("DE","NL"),
                pages_per_country=None,
                max_jobs=None,
                enrich_detail=False,
                session=SimpleNamespace(get=get),
                pace_seconds=0,
            )

        self.assertEqual([row["source"]["source_job_id"] for row in rows], ["100", "101"])
        self.assertTrue(any(event["stop_reason"] == "identical_country_result_set" for event in coverage))
        self.assertTrue(any(not event["complete"] for event in coverage))
        self.assertEqual({row["location"]["country_code"] for row in rows}, {None})
        self.assertEqual(
            {row["raw_extra"]["country_validation"] for row in rows},
            {"UNTRUSTED_IDENTICAL_RESULT_SET"},
        )

    def test_explicit_detail_country_mismatch_preserves_real_country_and_flags_coverage(self):
        listing = '<article>Germany <a href="/jobs/100">Research Fellow A</a></article>'
        detail = (
            "<html><body><h1>Research Fellow A</h1>"
            "<div>Country Spain Type of Contract Temporary</div>"
            "<p>" + ("Research description. " * 20) + "</p></body></html>"
        )
        gets = []

        def get(url, **kwargs):
            gets.append((url, kwargs.get("params")))
            if len(gets) == 1:
                return Response(FILTER_FORM)
            if len(gets) == 2:
                return Response(listing, filtered_url("job_country:794"))
            return Response(detail, "https://euraxess.ec.europa.eu/jobs/100")

        with capture_coverage() as coverage:
            rows = euraxess.collect(
                country_codes=("DE",),
                pages_per_country=None,
                max_jobs=None,
                enrich_detail=True,
                session=SimpleNamespace(get=get),
                pace_seconds=0,
            )

        self.assertEqual(rows[0]["location"]["country_code"], "ES")
        self.assertEqual(rows[0]["location"]["country_name"], "Spain")
        self.assertEqual(rows[0]["raw_extra"]["requested_country_code"], "DE")
        self.assertEqual(rows[0]["raw_extra"]["detail_country"], "Spain")
        self.assertEqual(rows[0]["raw_extra"]["country_validation"], "DETAIL_MISMATCH")
        mismatch = [event for event in coverage if event["stop_reason"] == "detail_country_mismatch"]
        self.assertEqual(len(mismatch), 1)
        self.assertFalse(mismatch[0]["complete"])

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
                SimpleNamespace(get=get),
                "GET",
                euraxess.SEARCH_URL,
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
