from types import SimpleNamespace
import unittest

from src.sources.shared import academicpositions
from src.sources.shared.pagination import capture_coverage


class Response:
    def __init__(self, *, text='', url='https://example.org', status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


class AcademicPositionsReaderFallbackTests(unittest.TestCase):
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
