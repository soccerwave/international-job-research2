import unittest
from types import SimpleNamespace

from src.sources.shared import academicpositions
from src.sources.shared.pagination import capture_coverage


class Response:
    def __init__(self, *, text='', url='https://academicpositions.com/jobs/country/germany', status_code=200):
        self.text=text
        self.url=url
        self.status_code=status_code
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


def listing_html(total, ids, *, next_href=None):
    links=''.join(
        f'<a href="/ad/university/research-fellow/{job_id}">Research Fellow {job_id}</a>'
        for job_id in ids
    )
    next_link=f'<a href="{next_href}">›</a>' if next_href else ''
    return f'<html><body><h1>{total} jobs in Germany</h1>{links}{next_link}</body></html>'


class AcademicPositionsStage45Tests(unittest.TestCase):
    def test_current_czech_country_slug_is_czechia(self):
        self.assertEqual(academicpositions.COUNTRY_SLUGS['CZ'], 'czechia')

    def test_first_page_404_is_clean_zero_for_known_country(self):
        calls=[]
        def get(url, **kwargs):
            calls.append((url, kwargs.get('params')))
            return Response(url=url, status_code=404)
        with capture_coverage() as events:
            rows=academicpositions.collect(
                country_codes=('IE',), max_pages_per_country=None, max_jobs=None,
                enrich_detail=False, session=SimpleNamespace(get=get),
            )
        self.assertEqual(rows, [])
        self.assertEqual(len(calls), 1)
        self.assertTrue(events[-1]['complete'])
        self.assertEqual(events[-1]['stop_reason'], 'empty_page')

    def test_paginator_stops_on_last_page_without_probing_nonexistent_page(self):
        calls=[]
        pages={
            1: listing_html(3, ('101','102'), next_href='?page=2'),
            2: listing_html(3, ('103',), next_href=None),
        }
        def get(url, **kwargs):
            page=(kwargs.get('params') or {}).get('page',1)
            calls.append(page)
            if page not in pages:
                return Response(url=url, status_code=404)
            return Response(text=pages[page], url=f'{url}?page={page}')
        with capture_coverage() as events:
            rows=academicpositions.collect(
                country_codes=('DE',), max_pages_per_country=None, max_jobs=None,
                enrich_detail=False, session=SimpleNamespace(get=get),
            )
        self.assertEqual([row['source']['source_job_id'] for row in rows], ['101','102','103'])
        self.assertEqual(calls, [1,2])
        self.assertTrue(events[-1]['complete'])
        self.assertIn(events[-1]['stop_reason'], {'advertised_total_reached','last_page'})

    def test_later_page_failure_remains_partial(self):
        def get(url, **kwargs):
            page=(kwargs.get('params') or {}).get('page',1)
            if page == 1:
                return Response(text=listing_html(4, ('101','102'), next_href='?page=2'), url=url)
            return Response(url=url, status_code=500)
        with capture_coverage() as events:
            rows=academicpositions.collect(
                country_codes=('DE',), max_pages_per_country=None, max_jobs=None,
                enrich_detail=False, session=SimpleNamespace(get=get),
            )
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(e['stop_reason']=='request_failed' and not e['complete'] for e in events))

    def test_parse_advertised_total_reads_country_heading(self):
        self.assertEqual(academicpositions.parse_advertised_total('<h1>101 jobs in The Netherlands</h1>'), 101)
        self.assertIsNone(academicpositions.parse_advertised_total('<h1>Browse jobs</h1>'))


if __name__ == '__main__':
    unittest.main()
