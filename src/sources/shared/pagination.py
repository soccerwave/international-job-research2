"""Pagination with explicit coverage evidence; None means no record/page cap."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urljoin, urlparse
import re
from bs4 import BeautifulSoup

_EVENTS = ContextVar('collection_coverage', default=None)


@contextmanager
def capture_coverage():
    events = []
    token = _EVENTS.set(events)
    try:
        yield events
    finally:
        _EVENTS.reset(token)


def record_coverage(source, reason, *, complete=False, **details):
    event = dict(source=source, stop_reason=reason, complete=complete, **details)
    events = _EVENTS.get()
    if events is not None:
        events.append(event)
    return event


def reached(rows, limit):
    return limit is not None and len(rows) >= limit


def _known_linkedin_result_window_limit(source, pages, exc):
    """LinkedIn guest search returns HTTP 400 when the result window reaches start=1000.

    The pinned donor CLI exposes 10 results per page, so after 100 successful pages
    the next request is page 101 / start=1000. Production evidence from 2026-10-03
    showed this exact boundary consistently across countries and queries. Treat only
    that precise condition as an expected endpoint ceiling; all earlier/different
    failures remain incomplete coverage.
    """
    if not str(source).startswith('linkedin_mads:') or pages != 100:
        return False
    text = f'{type(exc).__name__}: {exc}'.upper()
    return '400' in text and 'SEARCH_FAILED' in text


def paginate(fetch, *, source, max_jobs=None, max_pages=None, start=0):
    """fetch(page) returns (parsed rows, advertised total or None, has_next or None).

    Totals of zero on subsequent Workday pages do not replace the initial total.
    A failed later page preserves all earlier rows and records incomplete coverage,
    except the independently observed LinkedIn guest-search 1000-result window ceiling.
    """
    rows, seen = [], set()
    total = None
    pages = 0
    reason = 'unknown'
    complete = False
    error = None
    while True:
        try:
            batch, advertised, has_next = fetch(start + pages)
        except Exception as exc:
            if _known_linkedin_result_window_limit(source, pages, exc):
                reason = 'known_result_window_limit'
                complete = True
                error = None
                break
            reason, error = 'request_failed', f'{type(exc).__name__}: {exc}'
            if not pages:
                record_coverage(source, reason, pages=0, records=0, error=error)
                raise
            break
        pages += 1
        if advertised is not None and int(advertised) > 0:
            total = max(total or 0, int(advertised))
        if not batch:
            reason = 'empty_page'
            complete = total is None or len(seen) >= total
            break
        new = 0
        for row in batch:
            key = str(row['id'])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            new += 1
            if reached(rows, max_jobs):
                break
        if total is not None and len(seen) >= total:
            reason, complete = 'advertised_total_reached', True
            break
        if reached(rows, max_jobs):
            reason = 'configured_record_limit'
            break
        if not new:
            reason = 'repeated_page'
            break
        if has_next is False:
            reason = 'last_page'
            complete = total is None or len(seen) >= total
            break
        if max_pages is not None and pages >= max_pages:
            reason = 'configured_page_limit'
            break
    record_coverage(source, reason, complete=complete, pages=pages, records=len(rows),
                    advertised_total=total, error=error)
    return rows


def next_listing_url(html, base_url):
    """Follow same-origin pagination links, preferring the current listing path.

    Some boards expose unrelated anchors whose text/title contains "Next". A
    pagination link normally stays on the listing path and changes only query
    parameters, so same-path candidates are preferred. If a board legitimately
    paginates to a different path, the previous same-origin fallback is preserved.
    """
    soup = BeautifulSoup(html or '', 'html.parser')
    base = urlparse(base_url)
    base_path = base.path.rstrip('/') or '/'
    same_path = []
    fallback = []
    for a in soup.find_all('a', href=True):
        label = ' '.join([a.get_text(' ', strip=True), str(a.get('aria-label') or ''), str(a.get('title') or '')]).strip().lower()
        rel = a.get('rel') or []
        if 'next' not in rel and not re.search(r'\b(next|more jobs|suivant|suivante|volgende|weiter|nächste)\b|^[›»>]$', label):
            continue
        if a.get('aria-disabled') == 'true' or 'disabled' in (a.get('class') or []):
            continue
        href = str(a['href'])
        if href.startswith(('#', 'javascript:')):
            continue
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.netloc != base.netloc:
            continue
        fallback.append(url)
        if (parsed.path.rstrip('/') or '/') == base_path:
            same_path.append(url)
    if same_path:
        return same_path[0]
    return fallback[0] if fallback else None


def html_pages(session, url, parser, *, max_jobs=None, initial_response=None):
    current = url
    visited = set()
    first = initial_response
    def fetch(page):
        nonlocal current, first
        if current in visited:
            raise RuntimeError('Pagination URL repeated: ' + current)
        visited.add(current)
        if first is not None:
            response, first = first, None
        else:
            response = session.get(current, timeout=(10, 45), allow_redirects=True)
            response.raise_for_status()
        items = parser(response.text, response.url)
        next_url = next_listing_url(response.text, response.url)
        if not next_url and re.search(r'(?:javascript:|__doPostBack).*?(?:next|page)|(?:next|page).*?__doPostBack', response.text, re.I):
            record_coverage(url, 'unsupported_dynamic_pagination')
        current = next_url
        return items, None, bool(next_url)
    return paginate(fetch, source=url, max_jobs=max_jobs)
