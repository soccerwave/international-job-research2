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


    def test_cloudflare_challenge_falls_back_to_reader_listing(self):
        direct_calls=[]
        reader_calls=[]
        def direct_get(url, **kwargs):
            direct_calls.append(url)
            return Response(text='<html><title>Just a moment...</title><div>cf-chl-</div></html>', url=url, status_code=403)
        markdown='''Title: 2 jobs in Germany - Academic Positions

[Research Fellow A](http://academicpositions.com/ad/university/2026/research-fellow-a/101)
[Research Fellow B](https://academicpositions.com/de/ad/university/2026/research-fellow-b/102)
'''
        def reader_get(url, **kwargs):
            reader_calls.append((url, kwargs.get('headers') or {}))
            return Response(text=markdown, url=url, status_code=200)
        with capture_coverage() as events:
            rows=academicpositions.collect(
                country_codes=('DE',), max_pages_per_country=None, max_jobs=None,
                enrich_detail=False,
                session=SimpleNamespace(get=direct_get),
                reader_session=SimpleNamespace(get=reader_get),
            )
        self.assertEqual([row['source']['source_job_id'] for row in rows], ['101','102'])
        self.assertEqual(len(direct_calls), 1)
        self.assertEqual(len(reader_calls), 1)
        self.assertTrue(events[-1]['complete'])
        self.assertEqual(events[-1]['stop_reason'], 'advertised_total_reached')
        self.assertTrue(all((row.get('raw_extra') or {}).get('access_transport') == 'reader' for row in rows))

    def test_reader_uses_regional_route_when_root_remains_challenged(self):
        challenge='Title: Just a moment...\n\nEnable JavaScript and cookies to continue\n'
        regional='''Title: 3 jobber i Tsjekkia - Academic Positions

[Postdoctoral Researcher A](http://academicpositions.com/no/ad/university/2026/postdoctoral-researcher-a/201)
[Postdoctoral Researcher B](http://academicpositions.com/no/ad/university/2026/postdoctoral-researcher-b/202)
[Researcher C](http://academicpositions.com/no/ad/university/2026/researcher-c/203)
'''
        def direct_get(url, **kwargs):
            return Response(text='<title>Just a moment...</title><div>cf-chl-</div>', url=url, status_code=403)
        reader_urls=[]
        def reader_get(url, **kwargs):
            reader_urls.append(url)
            if '/no/jobs/country/czechia' in url:
                return Response(text=regional, url=url, status_code=200)
            return Response(text=challenge, url=url, status_code=200)
        with capture_coverage() as events:
            rows=academicpositions.collect(
                country_codes=('CZ',), max_pages_per_country=None, max_jobs=None,
                enrich_detail=False,
                session=SimpleNamespace(get=direct_get),
                reader_session=SimpleNamespace(get=reader_get),
            )
        self.assertEqual([row['source']['source_job_id'] for row in rows], ['201','202','203'])
        self.assertTrue(any('/no/jobs/country/czechia' in url for url in reader_urls))
        self.assertTrue(events[-1]['complete'])
        self.assertEqual(events[-1]['stop_reason'], 'last_page')

    def test_reader_detail_recovers_full_job_text(self):
        listing='''Title: 1 job in Germany - Academic Positions

[Postdoctoral Researcher](http://academicpositions.com/ad/university/2026/postdoctoral-researcher/301)
'''
        detail='''Title: Postdoctoral Researcher - Academic Positions

Markdown Content:
About the job
This postdoctoral research position studies exercise physiology, stress regulation, brain health, and human adaptation using longitudinal experimental methods. The successful candidate will work with interdisciplinary collaborators, prepare manuscripts, contribute to data analysis, and support research dissemination.

Requirements
Applicants should hold a PhD and have relevant research experience. Closing on: 2026-10-31
'''
        def direct_get(url, **kwargs):
            return Response(text='<title>Just a moment...</title><div>cf-chl-</div>', url=url, status_code=403)
        def reader_get(url, **kwargs):
            if '/ad/' in url:
                return Response(text=detail, url=url, status_code=200)
            return Response(text=listing, url=url, status_code=200)
        rows=academicpositions.collect(
            country_codes=('DE',), max_pages_per_country=None, max_jobs=None,
            enrich_detail=True,
            session=SimpleNamespace(get=direct_get),
            reader_session=SimpleNamespace(get=reader_get),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['position']['title_raw'], 'Postdoctoral Researcher')
        self.assertEqual(rows[0]['description']['detail_status'], 'FULL')
        self.assertIn('exercise physiology', rows[0]['description']['full_jd'].lower())
        self.assertEqual(rows[0]['dates']['deadline_raw'], '2026-10-31')


if __name__ == '__main__':
    unittest.main()