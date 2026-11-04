"""Offline regression gates for EURAXESS country semantics and pagination.

No network requests and no production routing changes.
"""
import unittest
from urllib.parse import parse_qs, urlparse

from src.sources.shared import euraxess


def _card(job_id, country, offer="JOB"):
    return (
        '<div id="job-teaser-content">'
        '<div class="ecl-content-block__label-container">'
        f'<span class="ecl-label">{offer}</span>'
        f'<span class="ecl-label">{country}</span>'
        '</div>'
        f'<a href="/jobs/{job_id}">Postdoctoral Researcher {job_id}</a>'
        '</div>'
    )


class EuraxessCoverageGates(unittest.TestCase):
    def test_filtered_cards_country_and_offer_match(self):
        html = _card(475379, "Germany") + _card(475350, "Germany")
        rows = euraxess.parse_listing(html)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["listing_country_name"], "Germany")
            self.assertEqual(row["listing_country_code"], "DE")
            self.assertEqual(row["offer_type"], "JOB")

    def test_foreign_country_must_not_be_silently_accepted(self):
        html = _card(475379, "Germany") + _card(475481, "United Kingdom")
        rows = euraxess.parse_listing(html)
        mismatches = [r for r in rows if not euraxess._country_matches_requested(
            r["listing_country_name"], "DE")]
        self.assertEqual([r["id"] for r in mismatches], ["475481"])

    def test_duplicate_pages_are_detectable_by_ids(self):
        first = euraxess.parse_listing(_card(475379, "Germany") + _card(475350, "Germany"))
        second = euraxess.parse_listing(_card(475350, "Germany") + _card(475155, "Germany"))
        first_ids = {r["id"] for r in first}
        next_ids = {r["id"] for r in second}
        self.assertEqual(next_ids - first_ids, {"475155"})
        repeated = euraxess.parse_listing(_card(475379, "Germany") + _card(475350, "Germany"))
        self.assertFalse({r["id"] for r in repeated} - first_ids)

    def test_filtered_url_keeps_both_facets_across_pages(self):
        from urllib.parse import urlencode
        base = euraxess.SEARCH_URL + "?" + urlencode(
            euraxess._filter_params("job_country:794", "offer_type:job_offer"))
        page = euraxess._increment_euraxess_page(base)
        self.assertEqual(parse_qs(urlparse(page).query)["page"], ["1"])
        euraxess._assert_filtered_url(page, "job_country:794", "offer_type:job_offer")


if __name__ == "__main__":
    unittest.main()
