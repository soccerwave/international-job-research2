import unittest
from types import SimpleNamespace

from src.sources.shared import common


class Response:
    def __init__(self, text='', url='https://example.org/job/1', status_code=200, headers=None):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = headers or {'content-type': 'text/html'}
        self.content = text.encode('utf-8')
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


def record(source_key, text, status):
    return common.make_record(
        source_key=source_key,
        source_kind='ATS',
        provider='Test Provider',
        source_job_id='1',
        listing_url='https://example.org/jobs',
        detail_url='https://example.org/job/1',
        title='Research Fellow',
        full_jd=text,
        detail_status=status,
    )


class FullJDSemanticsStage49Tests(unittest.TestCase):
    def test_status_helper_uses_evidence_not_length(self):
        short = 'short but complete detail'
        long = 'x' * 5000
        self.assertEqual(common.detail_status_from_text(short, complete_evidence=True), 'FULL')
        self.assertEqual(common.detail_status_from_text(long, complete_evidence=True), 'FULL')
        self.assertEqual(common.detail_status_from_text(short, complete_evidence=False), 'PARTIAL')
        self.assertEqual(common.detail_status_from_text(long, complete_evidence=False), 'PARTIAL')

    def test_registered_source_short_detail_is_full_even_if_collector_hint_is_partial(self):
        rec = record('workday_usyd', 'brief structured API description', 'PARTIAL')
        self.assertEqual(rec['description']['detail_status'], 'FULL')

    def test_registered_source_long_detail_is_full(self):
        rec = record('pageup_monash', 'x' * 5000, 'FULL')
        self.assertEqual(rec['description']['detail_status'], 'FULL')

    def test_unregistered_generic_html_is_partial_even_if_long_and_hint_says_full(self):
        rec = record('dvs', 'x' * 5000, 'FULL')
        self.assertEqual(rec['description']['detail_status'], 'PARTIAL')

    def test_unregistered_short_and_long_text_have_same_partial_semantics(self):
        short = record('unknown_html_source', 'short text', 'PARTIAL')
        long = record('unknown_html_source', 'x' * 5000, 'FULL')
        self.assertEqual(short['description']['detail_status'], 'PARTIAL')
        self.assertEqual(long['description']['detail_status'], 'PARTIAL')

    def test_empty_text_cannot_be_full(self):
        rec = record('workday_usyd', '', 'FULL')
        self.assertEqual(rec['description']['detail_status'], 'UNAVAILABLE')
        self.assertIn('FULL_JD_UNAVAILABLE', rec['classification']['review_codes'])

    def test_failure_status_is_preserved(self):
        rec = record('workday_usyd', '', 'FETCH_FAILED')
        self.assertEqual(rec['description']['detail_status'], 'FETCH_FAILED')

    def test_generic_html_fetch_is_partial_regardless_of_length(self):
        html = '<html><body><main>' + ('Long generic page text. ' * 100) + '</main></body></html>'
        session = SimpleNamespace(get=lambda *a, **k: Response(text=html))
        text, status = common.fetch_detail_text('https://example.org/job/1', session=session)
        self.assertGreater(len(text), 200)
        self.assertEqual(status, 'PARTIAL')


if __name__ == '__main__':
    unittest.main()
