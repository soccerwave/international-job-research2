import unittest
from types import SimpleNamespace

from src.sources.shared import jobs_ac_uk


class Response:
    def __init__(self, text='', url='https://www.jobs.ac.uk/job/TEST/research-fellow', status_code=200):
        self.text=text; self.url=url; self.status_code=status_code
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f'HTTP {self.status_code}')


def detail_html(*, country='United Kingdom', locality='Birmingham', placed='17th August 2026', closes='14th September 2026'):
    return f'''<html><head><script type="application/ld+json">{{
      "@context":"https://schema.org","@type":"JobPosting","title":"Research Fellow",
      "hiringOrganization":{{"@type":"Organization","name":"University of Birmingham"}},
      "jobLocation":{{"@type":"Place","address":{{"@type":"PostalAddress","addressLocality":"{locality}","addressCountry":"{country}"}}}}
    }}</script></head><body><main><h1>Research Fellow</h1><h3>University of Birmingham</h3>
    <div>Location: {locality} Salary: £42,254 Hours: Full Time Contract Type: Fixed-Term/Contract
    Placed On: {placed} Closes: {closes} Job Ref: 106991</div>
    <p>{'Research duties and project description. ' * 30}</p></main></body></html>'''


class JobsAcUkStage46Tests(unittest.TestCase):
    def test_detail_metadata_is_bounded_and_dates_are_cleaned(self):
        parsed=jobs_ac_uk.parse_detail(detail_html())
        self.assertEqual(parsed['location'],'Birmingham')
        self.assertEqual(parsed['country'],'United Kingdom')
        self.assertEqual(parsed['posted'],'17 August 2026')
        self.assertEqual(parsed['deadline'],'14 September 2026')
        self.assertLess(len(parsed['location']),100)

    def test_foreign_country_is_not_forced_to_gb(self):
        html=detail_html(country='Denmark', locality='Aarhus')
        def get(url, **kwargs):
            if '/search/' in url:
                return Response('<a href="/job/ABC123/research-fellow">Research Fellow</a>',url='https://www.jobs.ac.uk/search/')
            return Response(html,url=url)
        rows=jobs_ac_uk.collect(keywords=('research fellow',),pages_per_query=1,max_jobs=1,enrich_detail=True,session=SimpleNamespace(get=get))
        self.assertEqual(rows[0]['location']['country_code'],'DK')
        self.assertNotEqual(rows[0]['location']['country_code'],'GB')

    def test_unknown_location_remains_unknown_not_gb(self):
        html='''<html><body><main><h1>Research Fellow</h1><div>Location: Mystery Campus Salary: Competitive Placed On: 3rd September 2026 Closes: 20th September 2026 Job Ref: X</div><p>''' + ('description ' * 80) + '''</p></main></body></html>'''
        def get(url, **kwargs):
            if '/search/' in url:
                return Response('<a href="/job/ABC124/research-fellow">Research Fellow</a>',url='https://www.jobs.ac.uk/search/')
            return Response(html,url=url)
        rows=jobs_ac_uk.collect(keywords=('research fellow',),pages_per_query=1,max_jobs=1,enrich_detail=True,session=SimpleNamespace(get=get))
        self.assertIsNone(rows[0]['location']['country_code'])

    def test_normalized_dates_reach_record(self):
        html=detail_html()
        def get(url, **kwargs):
            if '/search/' in url:
                return Response('<a href="/job/ABC125/research-fellow">Research Fellow</a>',url='https://www.jobs.ac.uk/search/')
            return Response(html,url=url)
        row=jobs_ac_uk.collect(keywords=('research fellow',),pages_per_query=1,max_jobs=1,enrich_detail=True,session=SimpleNamespace(get=get))[0]
        self.assertTrue(row['dates']['posted_at'].startswith('2026-08-17'))
        self.assertTrue(row['dates']['deadline_at'].startswith('2026-09-14'))

    def test_location_label_cannot_consume_jd(self):
        html=detail_html(locality='Birmingham')
        parsed=jobs_ac_uk.parse_detail(html)
        self.assertNotIn('Research duties',parsed['location'])
        self.assertLess(len(parsed['location']),100)


if __name__=='__main__': unittest.main()
