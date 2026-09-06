import unittest
from types import SimpleNamespace

from src.sources.core import workday
from src.sources.shared.pagination import capture_coverage


class Response:
    def __init__(self, payload):
        self.payload = payload
    def json(self):
        return self.payload
    def raise_for_status(self):
        pass


def valid_row(i):
    return {
        'title': f'Research Fellow {i}',
        'externalPath': f'/job/Camperdown-Campus/Research-Fellow-{i}_{i:07d}-1',
    }


class WorkdaySydneyStage48Tests(unittest.TestCase):
    def test_usyd_stops_at_raw_advertised_window_even_with_one_unparseable_item(self):
        calls=[]
        first_page=[valid_row(i) for i in range(20)]
        pages={
            0: {'total':73,'jobPostings':first_page},
            20: {'total':0,'jobPostings':[valid_row(i) for i in range(20,40)]},
            40: {'total':0,'jobPostings':[valid_row(i) for i in range(40,60)]},
            60: {'total':0,'jobPostings':[valid_row(i) for i in range(60,72)] + [{'title':'Malformed row without path'}]},
            80: {'total':73,'jobPostings':first_page},
        }
        def post(url, **kw):
            offset=kw['json']['offset']; calls.append(offset)
            return Response(pages[offset])
        with capture_coverage() as events:
            rows=workday.discover(workday.TENANTS['usyd'],max_jobs=None,session=SimpleNamespace(post=post))
        self.assertEqual(calls,[0,20,40,60])
        self.assertEqual(len(rows),72)
        self.assertEqual(len({r['external_path'] for r in rows}),72)
        final=events[-1]
        self.assertTrue(final['complete'])
        self.assertEqual(final['stop_reason'],'advertised_total_window_reached')
        self.assertEqual(final['advertised_total'],73)
        self.assertEqual(final['raw_records'],73)
        self.assertEqual(final['skipped_unparseable'],1)

    def test_public_workday_id_contract_is_unchanged(self):
        row=workday.parse_search_payload({'jobPostings':[{
            'title':'Research Fellow in Multi-Omics Data Science',
            'externalPath':'/job/Camperdown-Campus/Research-Fellow-in-Multi-Omics-Data-Science_0152856-1',
        }]})[0]
        self.assertEqual(row['id'],'0152856-1')

    def test_non_usyd_tenant_keeps_shared_paginate_behavior(self):
        calls=[]
        def post(url, **kw):
            offset=kw['json']['offset']; calls.append(offset)
            batch=[valid_row(i) for i in range(offset,min(offset+20,49))]
            return Response({'total':49 if offset==0 else 0,'jobPostings':batch})
        with capture_coverage() as events:
            rows=workday.discover(workday.TENANTS['flinders'],max_jobs=None,session=SimpleNamespace(post=post))
        self.assertEqual(len(rows),49)
        self.assertEqual(calls,[0,20,40])
        self.assertTrue(events[-1]['complete'])


if __name__=='__main__':
    unittest.main()
