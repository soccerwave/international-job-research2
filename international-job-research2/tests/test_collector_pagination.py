import json
from contextlib import ExitStack
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.sources.shared.pagination import capture_coverage, paginate, next_listing_url
from src.sources.core import workday, smartrecruiters, pageup, university_vacancies
from src.sources.shared import academicpositions, jobs_ac_uk, linkedin_mads
from src.runtime.production_sources import production_source_map
from src.runtime.production_shards import PRODUCTION_SHARD_IDS, run_production_shard


class Response:
    def __init__(self, payload=None, text='', url='https://example.org/listing/'):
        self.payload, self.text, self.url, self.status_code = payload, text, url, 200
    def json(self): return self.payload
    def raise_for_status(self): pass


class PaginationTests(unittest.TestCase):
    def test_workday_reads_past_twenty_and_ignores_later_zero_total(self):
        calls=[]
        def post(url, **kw):
            q=kw['json'];calls.append(q['offset'])
            batch=[{'title':f'Research Fellow {i}', 'externalPath':f'/job/R{i:06}'}
                   for i in range(q['offset'],min(q['offset']+q['limit'],49))]
            return Response({'total':49 if q['offset']==0 else 0,'jobPostings':batch})
        with capture_coverage() as audit:
            rows=workday.discover(workday.TENANTS['flinders'],max_jobs=None,session=SimpleNamespace(post=post))
        self.assertEqual(len(rows),49)
        self.assertEqual(calls,[0,20,40])
        self.assertTrue(audit[-1]['complete'])

    def test_smartrecruiters_paginates_beyond_api_page_size(self):
        calls=[]
        def get(url, **kw):
            q=kw['params'];calls.append(q['offset'])
            return Response({'totalFound':125,'content':[{'id':str(i),'name':f'Research Fellow {i}'}
                for i in range(q['offset'],min(q['offset']+q['limit'],125))]})
        rows=smartrecruiters.collect(tenant_key='griffith',max_jobs=None,enrich_detail=False,session=SimpleNamespace(get=get))
        self.assertEqual(len(rows),125);self.assertEqual(calls,[0,100])

    def test_pageup_follows_more_jobs_and_keeps_generic_research_title(self):
        calls=[]
        def get(url, **kw):
            calls.append(url)
            html='<a href="/job/100/research">Research Fellow</a><a href="?page=2">More Jobs</a>' if len(calls)==1 else '<a href="/job/101/research">Postdoctoral Research Fellow</a>'
            return Response(text=html,url=url)
        with capture_coverage() as audit:
            rows=pageup.collect(tenant_key='monash',max_jobs=None,enrich_detail=False,session=SimpleNamespace(get=get))
        self.assertEqual(len(rows),2);self.assertEqual(len(calls),2);self.assertTrue(audit[-1]['complete'])

    def test_failed_later_page_preserves_rows_and_marks_partial(self):
        def fetch(page):
            if page==1: raise TimeoutError('temporary outage')
            return [{'id':'a'}],3,None
        with capture_coverage() as audit:
            rows=paginate(fetch,source='test')
        self.assertEqual(rows,[{'id':'a'}]);self.assertFalse(audit[-1]['complete'])
        self.assertEqual(audit[-1]['stop_reason'],'request_failed')

    def test_first_page_failure_is_not_successful_empty_source(self):
        with capture_coverage() as audit:
            with self.assertRaises(TimeoutError):
                paginate(lambda p: (_ for _ in ()).throw(TimeoutError()),source='test')
        self.assertFalse(audit[-1]['complete'])

    def test_repeated_page_stops_and_is_incomplete(self):
        calls=[]
        def fetch(p): calls.append(p);return [{'id':'same'}],None,None
        with capture_coverage() as audit: rows=paginate(fetch,source='test')
        self.assertEqual(len(rows),1);self.assertEqual(calls,[0,1]);self.assertFalse(audit[-1]['complete'])

    def test_short_page_does_not_imply_end(self):
        def fetch(p): return ([{'id':str(p)}] if p<3 else []),None,None
        with capture_coverage() as audit: rows=paginate(fetch,source='test')
        self.assertEqual(len(rows),3);self.assertTrue(audit[-1]['complete'])

    def test_early_empty_page_against_total_is_incomplete(self):
        with capture_coverage() as audit:
            paginate(lambda p: ([{'id':'a'}] if p==0 else [],3,None),source='test')
        self.assertFalse(audit[-1]['complete'])

    def test_positive_limit_is_explicit_and_visible(self):
        with capture_coverage() as audit:
            rows=paginate(lambda p: ([{'id':str(i)} for i in range(10)],10,None),source='test',max_jobs=3)
        self.assertEqual(len(rows),3);self.assertEqual(audit[-1]['stop_reason'],'configured_record_limit')

    def test_jobs_queries_do_not_starve_later_queries_when_first_page_duplicates(self):
        calls=[]
        def get(url,**kw):
            q=kw['params'];key=(q['keywords'],q['startIndex']);calls.append(key)
            ids={'a':{1:['1'],26:[]},'b':{1:['1'],26:['2'],51:[]}}[key[0]][key[1]]
            return Response(text=''.join(f'<a href="https://www.jobs.ac.uk/job/{i}/research">Research Fellow {i}</a>' for i in ids))
        rows=jobs_ac_uk.collect(keywords=('a','b'),pages_per_query=None,max_jobs=None,enrich_detail=False,session=SimpleNamespace(get=get))
        self.assertEqual(len(rows),2);self.assertIn(('b',26),calls)

    def test_failed_country_does_not_discard_or_starve_others(self):
        def get(url,**kw):
            if 'netherlands' in url:raise TimeoutError('blocked')
            page=kw['params'].get('page',1)
            return Response(text='<a href="/ad/university/title/12345">Research Fellow</a>' if page==1 else '',url=url)
        with capture_coverage() as audit:
            rows=academicpositions.collect(country_codes=('NL','DE'),max_pages_per_country=None,max_jobs=None,enrich_detail=False,session=SimpleNamespace(get=get))
        self.assertEqual(len(rows),1);self.assertTrue(any(not x['complete'] for x in audit))

    def test_linkedin_uses_donor_page_flag_without_client_side_slice(self):
        calls=[]
        def runner(repo,args):
            page=int(args[args.index('--page')+1]);calls.append(args)
            results=[{'id':str(page),'title':'Research Fellow','location':'Ireland'}] if page<3 else []
            return SimpleNamespace(returncode=0,stdout=json.dumps({'results':results}),stderr='')
        with patch.object(linkedin_mads,'resolve_repo',return_value=Path('/tmp')):
            rows=linkedin_mads.collect(locations=('Ireland',),queries=('research fellow',),limit_per_search=None,max_jobs=None,enrich_detail=False,runner=runner)
        self.assertEqual(len(rows),2);self.assertEqual(len(calls),3)
        self.assertTrue(all('--limit' not in call for call in calls))

    def test_university_vacancies_uses_all_api_pages(self):
        def get(url,**kw):
            p=kw['params']['page']
            return Response({'data':{'jobPosts':[{'id':p,'title':'Research Fellow'}], 'pagination':{'total':2}}})
        rows=university_vacancies.collect(max_jobs=None,enrich_detail=False,session=SimpleNamespace(get=get))
        self.assertEqual(len(rows),2)

    def test_production_map_passes_none_to_every_collector(self):
        from src.runtime import production_sources as sources
        with ExitStack() as stack:
            stack.enter_context(patch.object(sources, '_linkedin_repo', return_value='/tmp'))
            for module in [sources.cnrs, sources.corehr, sources.pageup, sources.smartrecruiters,
                           sources.successfactors, sources.university_vacancies, sources.workday,
                           sources.academicpositions, sources.dvs, sources.ecss, sources.euraxess,
                           sources.fens, sources.jobs_ac_uk, sources.linkedin_mads]:
                stack.enter_context(patch.object(module, 'collect', side_effect=lambda **kw: kw))
            for name in ['collect_academictransfer','collect_academics','collect_innsbruck']:
                stack.enter_context(patch.object(sources.portals, name, side_effect=lambda **kw: kw))
            specs=production_source_map()
            for shard in specs.values():
                for spec in shard:
                    kwargs=spec.collector()
                    self.assertIsNone(kwargs['max_jobs'],spec.source_id)
                    for name in ['pages_per_country','max_pages_per_country','pages_per_query','max_pages','limit_per_search']:
                        if name in kwargs: self.assertIsNone(kwargs[name], spec.source_id)
        self.assertEqual(set(specs), set(PRODUCTION_SHARD_IDS))

    def test_partial_pagination_reaches_production_diagnostics(self):
        def collect():
            def fetch(page):
                if page:raise TimeoutError('page two')
                return [{'id':'a'}],2,None
            paginate(fetch,source='fake')
            return []
        spec=SimpleNamespace(source_id='fake',report_key='fake',collector=collect)
        with tempfile.TemporaryDirectory() as tmp, patch('src.runtime.production_shards.production_specs',return_value={'fake':[spec]}):
            d=run_production_shard(run_id='test',shard_id='fake',output_root=Path(tmp))
        self.assertEqual(d.status.value,'PARTIAL')
        self.assertEqual(d.metadata['source_results'][0]['status'],'PARTIAL')
        self.assertTrue(any('Incomplete coverage' in x for x in d.warnings))

    def test_next_link_stays_on_same_origin(self):
        self.assertIsNone(next_listing_url('<a rel="next" href="https://evil.example/">Next</a>','https://example.org/'))


if __name__=='__main__':unittest.main()
