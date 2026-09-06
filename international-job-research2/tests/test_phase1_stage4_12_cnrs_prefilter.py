from __future__ import annotations

import unittest
from unittest.mock import patch

from src.runtime.production_sources import production_source_map
from src.sources.core import cnrs


class CNRSStage412Tests(unittest.TestCase):
    def test_parser_keeps_offer_without_old_role_keywords(self):
        html = '''
        <div class="job">
          <a href="/Offres/CDD/UMR1234-ABCDEF-001/Default.aspx">Ingénieur de recherche en neuroimagerie (H/F)</a>
          <span>IT en contrat CDD · Doctorat</span>
        </div>
        '''
        rows = cnrs.parse_listing(html)
        self.assertEqual(len(rows), 1)
        self.assertIn("Ingénieur de recherche", rows[0]["title"])

    def test_parser_still_keeps_postdoctoral_offer(self):
        html = '''
        <article>
          <a href="https://emploi.cnrs.fr/Offres/CDD/UMR5678-QWERTY-002/Default.aspx">Chercheur postdoctoral (H/F)</a>
        </article>
        '''
        rows = cnrs.parse_listing(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://emploi.cnrs.fr/Offres/CDD/UMR5678-QWERTY-002/Default.aspx")

    def test_non_offer_and_external_links_are_excluded(self):
        html = '''
        <a href="/Offres/Recherche.aspx">Nos offres</a>
        <a href="/Unites/UMR1234/Offres.aspx">Offres de l'unité</a>
        <a href="https://example.org/Offres/CDD/UMR1234-ABC-001/Default.aspx">External</a>
        '''
        self.assertEqual(cnrs.parse_listing(html), [])

    def test_duplicate_offer_preserves_legacy_source_id(self):
        html = '''
        <a href="/Offres/CDD/UMR7116-SIMCOR-010/Default.aspx">Titre A</a>
        <a href="/Offres/CDD/UMR7116-SIMCOR-010/Default.aspx">Titre A duplicate</a>
        '''
        rows = cnrs.parse_listing(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "offres-cdd-umr7116-simcor-010-default-aspx")

    def test_production_routes_cnrs_to_recall_safe_collector(self):
        calls = production_source_map(limit=1)["germany-france-primary"]
        cnrs_call = next(call for call in calls if call.source_id == "cnrs_emploi")
        self.assertEqual(cnrs_call.report_key, "cnrs_emploi")
        with patch("src.runtime.production_sources.cnrs.collect", return_value=[]) as mocked:
            self.assertEqual(cnrs_call.collector(), [])
            mocked.assert_called_once_with(max_jobs=1)


if __name__ == "__main__":
    unittest.main()
