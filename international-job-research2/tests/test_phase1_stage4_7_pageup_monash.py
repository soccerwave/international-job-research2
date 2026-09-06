import unittest
from types import SimpleNamespace

from src.sources.core import pageup
from src.sources.shared.pagination import capture_coverage


class Response:
    def __init__(self, text='', url='https://careers.pageuppeople.com/513/ind/en/listing/', status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


def listing(job_id, title, next_href=None, next_label='More Jobs 20'):
    nxt = f'<a href="{next_href}">{next_label}</a>' if next_href else ''
    return (
        '<html><body><div class="job">'
        f'<a href="/513/ind/en/job/{job_id}/{title.lower().replace(" ", "-")}">{title}</a>'
        '</div>' + nxt + '</body></html>'
    )


class PageUpMonashStage47Tests(unittest.TestCase):
    def test_forward_page_link_is_accepted(self):
        html = listing('1001', 'Research Fellow', '?page=2&page-items=20')
        url = pageup.monash_next_listing_url(
            html, 'https://careers.pageuppeople.com/513/ind/en/listing/'
        )
        self.assertEqual(
            url,
            'https://careers.pageuppeople.com/513/ind/en/listing/?page=2&page-items=20',
        )

    def test_root_more_jobs_link_is_not_pagination(self):
        html = listing('1001', 'Research Fellow', '/513/ind/en/listing/', 'More Jobs')
        self.assertIsNone(pageup.monash_next_listing_url(
            html,
            'https://careers.pageuppeople.com/513/ind/en/listing/?page=4&page-items=20',
        ))

    def test_self_or_backward_page_is_not_pagination(self):
        html = (
            '<a href="?page=3&page-items=20">More Jobs</a>'
            '<a href="?page=4&page-items=20">Next</a>'
        )
        self.assertIsNone(pageup.monash_next_listing_url(
            html,
            'https://careers.pageuppeople.com/513/ind/en/listing/?page=4&page-items=20',
        ))

    def test_monash_collection_stops_cleanly_on_terminal_root_link(self):
        base = 'https://careers.pageuppeople.com/513/ind/en/listing/'
        pages = {
            base: Response(listing('1001', 'Research Fellow', '?page=2&page-items=20'), base),
            base + '?page=2&page-items=20': Response(
                listing('1002', 'Lecturer', '/513/ind/en/listing/', 'More Jobs'),
                base + '?page=2&page-items=20',
            ),
        }
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            return pages[url]

        with capture_coverage() as events:
            rows = pageup.collect(
                tenant_key='monash', max_jobs=None, enrich_detail=False,
                session=SimpleNamespace(get=get),
            )
        self.assertEqual(len(rows), 2)
        self.assertEqual(calls, [base, base + '?page=2&page-items=20'])
        self.assertEqual(events[-1]['stop_reason'], 'last_page')
        self.assertTrue(events[-1]['complete'])

    def test_deakin_and_unsw_do_not_use_monash_specific_path(self):
        self.assertNotEqual(pageup.TENANTS['deakin'].key, 'monash')
        self.assertNotEqual(pageup.TENANTS['unsw'].key, 'monash')


if __name__ == '__main__':
    unittest.main()
