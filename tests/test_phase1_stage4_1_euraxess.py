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


FILTER_FORM_NO_OFFER = """
<form method="post" action="/jobs/search">
  <select name="job_country[]">
    <option value="794">Germany</option>
  </select>
  <button type="submit" name="op" value="Apply filters">Apply filters</button>
</form>
"""


def selected_form(code):
    country_value = {"DE": "794", "NL": "798"}[code]
    country_label = {"DE": "Germany", "NL": "Netherlands"}[code]
    other_value = "798" if code == "DE" else "794"
    other_label = "Netherlands" if code == "DE" else "Germany"
    return f"""
<form method="post" action="/jobs/search">
  <select name="job_country[]">
    <option value="{country_value}" selected>{country_label}</option>
    <option value="{other_value}">{other_label}</option>
  </select>
  <select name="offer_type[]"><option value="job_offer" selected>Job Offer</option></select>
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


def global_card(job_id, title, country=None, offer_type="JOB"):
    country_label = (
        f'<li class="ecl-content-block__label-item">'
        f'<span class="ecl-label ecl-label--highlight">{country}</span></li>'
        if country else ""
    )
    return f"""
<div id="job-teaser-content">
  <div class="label-thumbnail-wrapper">
    <ul class="ecl-content-block__label-container">
      <li class="ecl-content-block__label-item">
        <span class="ecl-label ecl-label--low">{offer_type}</span>
      </li>
      {country_label}
    </ul>
  </div>
  <article class="ecl-content-item">
    <div class="ecl-content-block ecl-content-item__content-block">
      <h3 class="ecl-content-block__title">
        <a class="ecl-link ecl-link--standalone" href="/jobs/{job_id}"><span>{title}</span></a>
      </h3>
    </div>
  </article>
</div>
"""


class EuraxessStage41Tests(unittest.TestCase):
    def test_discovers_current_get_facets_dynamically(self):
        facets = euraxess.discover_country_facets(FILTER_FORM)
        self.assertEqual(facets["germany"], "job_country:794")
        self.assertEqual(facets["netherlands"], "job_country:798")
        self.assertEqual(euraxess.discover_offer_type_facet(FILTER_FORM), "offer_type:job_offer")

    def test_parse_listing_extracts_structured_offer_type_and_country(self):
        rows = euraxess.parse_listing(global_card("100", "Research Fellow", "Germany"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["offer_type"], "JOB")
        self.assertEqual(rows[0]["listing_country_name"], "Germany")
        self.assertEqual(rows[0]["listing_country_code"], "DE")
        self.assertIn("JOB Germany", rows[0]["context"])

    def test_uses_get_facets_and_follows_filtered_next_link_unchanged(self):
        next_href = "?f%5B0%5D=job_country%3A794&f%5B1%5D=offer_type%3Ajob_offer&page=1"
        page1 = selected_form("DE") + (
            '<article>Germany <a href="/jobs/100">Research Fellow A</a></article>'
            f'<a rel="next" href="{next_href}">Next</a>'
        )
        page2 = selected_form("DE") + '<article>Germany <a href="/jobs/101">Research Fellow B</a></article>'
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
                country_codes=("DE",), pages_per_country=None, max_jobs=None,
                enrich_detail=False, session=SimpleNamespace(get=get), pace_seconds=0,
            )

        self.assertEqual([row["source"]["source_job_id"] for row in rows], ["100", "101"])
        self.assertEqual(
            gets[1],
            (euraxess.SEARCH_URL, [("f[0]", "job_country:794"), ("f[1]", "offer_type:job_offer")]),
        )
        self.assertEqual(gets[2], (euraxess.SEARCH_URL + next_href, None))
        self.assertEqual(rows[0]["raw_extra"]["filter_transport"], "GET_FACET")
        self.assertTrue(all(event["complete"] for event in coverage))

    def test_semantically_unfiltered_country_filter_falls_back_to_global_scan(self):
        stale_filtered = FILTER_FORM + global_card("999", "Global Wrong Result", "Croatia")
        global_page1 = (
            global_card("200", "Croatian Job", "Croatia")
            + global_card("201", "German Funding", "Germany", offer_type="FUNDING")
            + '<a rel="next" href="/jobs/search?page=1">Next</a>'
        )
        global_page2 = global_card("100", "German Research Fellow", "Germany")
        gets = []

        def get(url, **kwargs):
            gets.append((url, kwargs.get("params")))
            if len(gets) == 1:
                return Response(FILTER_FORM)
            if len(gets) == 2:
                return Response(stale_filtered, filtered_url("job_country:794"))
            if len(gets) == 3:
                return Response(global_page1, euraxess.SEARCH_URL)
            return Response(global_page2, euraxess.SEARCH_URL + "?page=1")

        with capture_coverage() as coverage:
            rows = euraxess.collect(
                country_codes=("DE",), pages_per_country=2, max_jobs=None,
                enrich_detail=False, session=SimpleNamespace(get=get), pace_seconds=0,
            )

        self.assertEqual([row["source"]["source_job_id"] for row in rows], ["100"])
        self.assertEqual(rows[0]["location"]["country_code"], "DE")
        self.assertEqual(rows[0]["raw_extra"]["filter_transport"], "GLOBAL_LISTING_FALLBACK")
        self.assertEqual(rows[0]["raw_extra"]["listing_country"], "Germany")
        self.assertEqual(rows[0]["raw_extra"]["country_validation"], "LISTING_CARD_VALIDATED")
        self.assertIn("rendered country filter is inactive", rows[0]["raw_extra"]["fallback_reason"])
        self.assertTrue(all(event["complete"] for event in coverage), coverage)

    def test_missing_offer_facet_uses_global_listing_fallback(self):
        global_page = global_card("150", "German Job Without Offer Facet", "Germany")
        gets = []

        def get(url, **kwargs):
            gets.append((url, kwargs.get("params")))
            if len(gets) == 1:
                return Response(FILTER_FORM_NO_OFFER)
            return Response(global_page, euraxess.SEARCH_URL)

        with capture_coverage() as coverage:
            rows = euraxess.collect(
                country_codes=("DE",), pages_per_country=None, max_jobs=None,
                enrich_detail=False, session=SimpleNamespace(get=get), pace_seconds=0,
            )

        self.assertEqual([row["source"]["source_job_id"] for row in rows], ["150"])
        self.assertEqual(rows[0]["raw_extra"]["filter_transport"], "GLOBAL_LISTING_FALLBACK")
        self.assertIsNone(rows[0]["raw_extra"]["offer_type_facet"])
        self.assertIn("Job Offer facet missing", rows[0]["raw_extra"]["fallback_reason"])
        self.assertTrue(all(event["complete"] for event in coverage), coverage)

    def test_identical_filtered_result_sets_are_discarded_and_global_fallback_wins(self):
        same_body = (
            '<article><a href="/jobs/300">Duplicated A</a></article>'
            '<article><a href="/jobs/301">Duplicated B</a></article>'
        )
        de_filtered = selected_form("DE") + same_body
        nl_filtered = selected_form("NL") + same_body
        global_page = (
            global_card("400", "German Global Job", "Germany")
            + global_card("401", "Dutch Global Job", "Netherlands")
        )
        gets = []

        def get(url, **kwargs):
            gets.append((url, kwargs.get("params")))
            if len(gets) == 1:
                return Response(FILTER_FORM)
            if len(gets) == 2:
                return Response(de_filtered, filtered_url("job_country:794"))
            if len(gets) == 3:
                return Response(nl_filtered, filtered_url("job_country:798"))
            return Response(global_page, euraxess.SEARCH_URL)

        with capture_coverage() as coverage:
            rows = euraxess.collect(
                country_codes=("DE", "NL"), pages_per_country=None, max_jobs=None,
                enrich_detail=False, session=SimpleNamespace(get=get), pace_seconds=0,
            )

        self.assertEqual(
            [row["source"]["source_job_id"] for row in rows],
            ["400", "401"],
        )
        self.assertEqual(
            {row["raw_extra"]["filter_transport"] for row in rows},
            {"GLOBAL_LISTING_FALLBACK"},
        )
        self.assertTrue(all(event["complete"] for event in coverage))

    def test_global_fallback_resolves_missing_card_country_from_detail(self):
        stale_filtered = FILTER_FORM + global_card("999", "Wrong Result", "Croatia")
        global_page = global_card("500", "Country Missing Research Fellow", None)
        detail = (
            "<html><body><h1>Country Missing Research Fellow</h1>"
            "<dl><dt>Organisation/Company</dt><dd>Example University</dd>"
            "<dt>Application Deadline</dt><dd>30 Sep 2026 - 12:00 (UTC)</dd>"
            "<dt>Country</dt><dd>Germany</dd></dl>"
            "<p>" + ("Research description. " * 20) + "</p></body></html>"
        )
        gets = []

        def get(url, **kwargs):
            gets.append((url, kwargs.get("params")))
            if len(gets) == 1:
                return Response(FILTER_FORM)
            if len(gets) == 2:
                return Response(stale_filtered, filtered_url("job_country:794"))
            if len(gets) == 3:
                return Response(global_page, euraxess.SEARCH_URL)
            return Response(detail, "https://euraxess.ec.europa.eu/jobs/500")

        with capture_coverage() as coverage:
            rows = euraxess.collect(
                country_codes=("DE",), pages_per_country=None, max_jobs=None,
                enrich_detail=True, session=SimpleNamespace(get=get), pace_seconds=0,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"]["source_job_id"], "500")
        self.assertEqual(rows[0]["location"]["country_code"], "DE")
        self.assertEqual(rows[0]["raw_extra"]["filter_transport"], "GLOBAL_LISTING_FALLBACK")
        self.assertEqual(rows[0]["raw_extra"]["detail_country"], "Germany")
        self.assertEqual(rows[0]["raw_extra"]["country_validation"], "DETAIL_MATCH")
        self.assertTrue(all(event["complete"] for event in coverage))

    def test_explicit_detail_country_mismatch_preserves_real_country_and_flags_coverage(self):
        listing = selected_form("DE") + '<article>Germany <a href="/jobs/100">Research Fellow A</a></article>'
        detail = (
            "<html><body><h1>Research Fellow A</h1>"
            "<dl><dt>Organisation/Company</dt><dd>Example University</dd>"
            "<dt>Application Deadline</dt><dd>30 Sep 2026 - 12:00 (UTC)</dd>"
            "<dt>Country</dt><dd>Spain</dd><dt>Type of Contract</dt><dd>Temporary</dd></dl>"
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
                country_codes=("DE",), pages_per_country=None, max_jobs=None,
                enrich_detail=True, session=SimpleNamespace(get=get), pace_seconds=0,
            )

        self.assertEqual(rows[0]["location"]["country_code"], "ES")
        self.assertEqual(rows[0]["location"]["country_name"], "Spain")
        self.assertEqual(rows[0]["raw_extra"]["requested_country_code"], "DE")
        self.assertEqual(rows[0]["raw_extra"]["detail_country"], "Spain")
        self.assertEqual(rows[0]["raw_extra"]["country_validation"], "DETAIL_MISMATCH")
        mismatch = [event for event in coverage if event["stop_reason"] == "detail_country_mismatch"]
        self.assertEqual(len(mismatch), 1)
        self.assertFalse(mismatch[0]["complete"])

    def test_structured_detail_metadata_ignores_filter_page_country_text(self):
        html = """
        <html><body>
          <div>Filter by Country Austria Belgium Germany Netherlands</div>
          <div>Posted on: 18 September 2026</div>
          <dl>
            <dt>Organisation/Company</dt><dd>Delft University of Technology</dd>
            <dt>Application Deadline</dt><dd>15 Oct 2026 - 21:59 (UTC)</dd>
            <dt>Country</dt><dd>Netherlands</dd>
            <dt>Type of Contract</dt><dd>Temporary</dd>
          </dl>
        </body></html>
        """
        meta = euraxess.parse_detail_metadata(html)
        self.assertEqual(meta["institution"], "Delft University of Technology")
        self.assertEqual(meta["deadline"], "15 Oct 2026 - 21:59 (UTC)")
        self.assertEqual(meta["country"], "Netherlands")
        self.assertEqual(meta["posted"], "18 September 2026")

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
                SimpleNamespace(get=get), "GET", euraxess.SEARCH_URL,
                attempts=3, pace_seconds=0,
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
