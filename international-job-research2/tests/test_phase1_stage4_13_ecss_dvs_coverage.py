from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.sources.shared import dvs, ecss
from src.sources.shared.pagination import capture_coverage


class Response:
    def __init__(self, text: str, url: str):
        self.text = text
        self.url = url
        self.status_code = 200

    def raise_for_status(self):
        return None


class Stage413CoverageTests(unittest.TestCase):
    @staticmethod
    def ecss_html(count: int = 2) -> str:
        rows = []
        for i in range(1, count + 1):
            rows.append(
                f'<tr><td>01.09.2026</td><td>30.09.2026</td><td>Research Fellow {i}</td>'
                f'<td>University {i}</td><td>Germany</td><td><a href="/files/{1000+i}.pdf">PDF</a></td></tr>'
            )
        return '<table>' + ''.join(rows) + '</table>'

    @staticmethod
    def dvs_html(count: int = 2) -> str:
        rows = []
        for i in range(1, count + 1):
            rows.append(
                f'<div>University {i}<br/>Research Fellow {i}<br/>Bewerbungsschluss: 30.09.2026 '
                f'<a href="/stellenboerse/{2000+i}">mehr...</a></div>'
            )
        return ''.join(rows)

    def test_ecss_uncapped_emits_complete_single_page_event(self):
        session = SimpleNamespace(get=lambda *a, **k: Response(self.ecss_html(), ecss.LISTING_URL))
        with capture_coverage() as events:
            rows = ecss.collect(max_jobs=None, enrich_detail=False, session=session)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['source'], 'ecss')
        self.assertEqual(events[0]['stop_reason'], 'single_page_complete')
        self.assertTrue(events[0]['complete'])
        self.assertEqual(events[0]['records'], 2)
        self.assertEqual(events[0]['discovered_records'], 2)

    def test_ecss_bounded_run_reports_incomplete_limit(self):
        session = SimpleNamespace(get=lambda *a, **k: Response(self.ecss_html(3), ecss.LISTING_URL))
        with capture_coverage() as events:
            rows = ecss.collect(max_jobs=1, enrich_detail=False, session=session)
        self.assertEqual(len(rows), 1)
        self.assertEqual(events[0]['stop_reason'], 'configured_record_limit')
        self.assertFalse(events[0]['complete'])
        self.assertEqual(events[0]['discovered_records'], 3)
        self.assertEqual(events[0]['configured_record_limit'], 1)

    def test_dvs_uncapped_emits_complete_single_page_event(self):
        session = SimpleNamespace(get=lambda *a, **k: Response(self.dvs_html(), dvs.LISTING_URL))
        with capture_coverage() as events:
            rows = dvs.collect(max_jobs=None, enrich_detail=False, session=session)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['source'], 'dvs')
        self.assertEqual(events[0]['stop_reason'], 'single_page_complete')
        self.assertTrue(events[0]['complete'])
        self.assertEqual(events[0]['records'], 2)
        self.assertEqual(events[0]['discovered_records'], 2)

    def test_dvs_bounded_run_reports_incomplete_limit(self):
        session = SimpleNamespace(get=lambda *a, **k: Response(self.dvs_html(3), dvs.LISTING_URL))
        with capture_coverage() as events:
            rows = dvs.collect(max_jobs=1, enrich_detail=False, session=session)
        self.assertEqual(len(rows), 1)
        self.assertEqual(events[0]['stop_reason'], 'configured_record_limit')
        self.assertFalse(events[0]['complete'])
        self.assertEqual(events[0]['discovered_records'], 3)
        self.assertEqual(events[0]['configured_record_limit'], 1)

    def test_empty_valid_single_page_is_explicit_complete_zero(self):
        for module in (ecss, dvs):
            session = SimpleNamespace(get=lambda *a, _m=module, **k: Response('', _m.LISTING_URL))
            with capture_coverage() as events:
                rows = module.collect(max_jobs=None, enrich_detail=False, session=session)
            self.assertEqual(rows, [])
            self.assertEqual(events[0]['stop_reason'], 'single_page_complete')
            self.assertTrue(events[0]['complete'])
            self.assertEqual(events[0]['records'], 0)


if __name__ == '__main__':
    unittest.main()
