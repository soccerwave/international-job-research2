"""Regression tests for CoreHR's POST-based Next navigation."""
import unittest
from types import SimpleNamespace
from src.sources.core import corehr
from src.sources.shared.pagination import capture_coverage


URL = "https://my.corehr.com/pls/trrecruit/erq_search_version_4.start_search_with_params"


def page(start, end, total, *, next_page=True):
    links = "".join(
        f'<tr><td><a href="javascript:viewTheJobSpec(\'{n:06d}\')">Research Fellow {n}</a></td></tr>'
        for n in range(start, end + 1)
    )
    form = ('<a href="#" onclick="document.searchv4navigateresultsforward.submit()">Next</a>'
            '<form name="searchv4navigateresultsforward" method="post" '
            'action="erq_search_version_4.start_search_with_params">'
            f'<input type="hidden" name="p_page" value="{end + 1}">'
            '<input type="hidden" name="p_company" value="1"></form>') if next_page else ""
    return f'<html><span>Displaying {start} to {end} of {total}</span>{links}{form}</html>'


class Response:
    def __init__(self, html):
        self.text, self.url = html, URL
    def raise_for_status(self):
        pass


class Session:
    def __init__(self, pages, fail_at=None):
        self.pages, self.fail_at, self.posts = pages, fail_at, []
    def post(self, url, **kwargs):
        self.posts.append(kwargs["data"])
        index = len(self.posts)
        if self.fail_at == index:
            raise TimeoutError("Later CoreHR page failed")
        return Response(self.pages[index])


class CoreHRPostPaginationTests(unittest.TestCase):
    def test_all_pages_collected_and_coverage_complete(self):
        pages = [page(1, 10, 22), page(11, 20, 22), page(21, 22, 22, next_page=False)]
        session = Session(pages)
        with capture_coverage() as events:
            rows = corehr._paginate_corehr_results(session, Response(pages[0]), "tcd")
        self.assertEqual(len(rows), 22)
        self.assertEqual(len({r["id"] for r in rows}), 22)
        self.assertEqual(len(session.posts), 2)
        self.assertIn(("p_page", "11"), session.posts[0])
        self.assertTrue(events[-1]["complete"])
        self.assertEqual(events[-1]["advertised_total"], 22)

    def test_missing_next_against_total_marked_incomplete(self):
        first = page(1, 10, 22, next_page=False)
        with capture_coverage() as events:
            rows = corehr._paginate_corehr_results(Session([first]), Response(first), "tcd")
        self.assertEqual(len(rows), 10)
        self.assertFalse(events[-1]["complete"])

    def test_later_post_failure_keeps_first_page_and_reports_partial(self):
        first = page(1, 10, 22)
        with capture_coverage() as events:
            rows = corehr._paginate_corehr_results(Session([first], fail_at=1), Response(first), "tcd")
        self.assertEqual(len(rows), 10)
        self.assertFalse(events[-1]["complete"])
        self.assertEqual(events[-1]["stop_reason"], "request_failed")

    def test_cross_origin_post_rejected(self):
        html = ('<a href="#" onclick="document.searchv4navigateresultsforward.submit()">Next</a>'
                '<form name="searchv4navigateresultsforward" '
                'action="https://other.example/collect"></form>')
        with self.assertRaises(ValueError):
            corehr._next_results_post(html, URL)


if __name__ == "__main__":
    unittest.main()
