from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from .pagination import next_listing_url, paginate, reached, record_coverage
from .common import CODE_TO_COUNTRY_NAME, clean, make_record, make_session

SOURCE_KEY = "euraxess"
PROVIDER = "EURAXESS"
SEARCH_URL = "https://euraxess.ec.europa.eu/jobs/search"
TARGET_CODES = ("NL","DE","IE","GB","BE","FR","AT","IT","PT","CZ","PL","LU")
JOB_RE = re.compile(r"/jobs/(\d+)(?:[/?#]|$)", re.I)
GENERIC_DETAIL_TITLES = {"job offer", "job", "jobs", "offer"}
COUNTRY_LABEL_ALIASES = {
    "GB": ("United Kingdom", "UK"),
    "CZ": ("Czechia", "Czech Republic"),
}


def discover_country_facets(html: str) -> dict[str, str]:
    """Return EURAXESS country labels mapped to stable form option values."""
    soup = BeautifulSoup(html or "", "html.parser")
    result: dict[str,str] = {}
    options = soup.select('select[name="job_country[]"] option') or soup.find_all("option")
    for option in options:
        value = clean(option.get("value"))
        label = clean(option.get_text(" ", strip=True))
        if not value or not label:
            continue
        if value.startswith("job_country:"):
            facet = value
        elif value.isdigit():
            facet = f"job_country:{value}"
        else:
            continue
        result[label.lower()] = facet
    return result


def _facet_for_code(facets: dict[str, str], code: str) -> str | None:
    labels = COUNTRY_LABEL_ALIASES.get(code) or (CODE_TO_COUNTRY_NAME.get(code) or "",)
    for label in labels:
        facet = facets.get(clean(label).lower())
        if facet:
            return facet
    return None


def _retry_after_seconds(response: Any, attempt: int) -> float:
    headers = getattr(response, "headers", {}) or {}
    raw = clean(headers.get("Retry-After"))
    if raw:
        try:
            return max(0.0, min(float(raw), 60.0))
        except ValueError:
            try:
                target = parsedate_to_datetime(raw)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                return max(0.0, min((target - datetime.now(timezone.utc)).total_seconds(), 60.0))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(5.0 * (2.0 ** attempt), 60.0)


def _request(
    session,
    method: str,
    url: str,
    *,
    params=None,
    data=None,
    attempts: int = 5,
    pace_seconds: float = 1.25,
):
    """EURAXESS-specific bounded request retries with Retry-After support."""
    method = method.upper()
    call = session.post if method == "POST" else session.get
    last = None
    for attempt in range(attempts):
        if pace_seconds > 0:
            time.sleep(pace_seconds)
        kwargs = {"timeout": (10,45), "allow_redirects": True}
        if params is not None:
            kwargs["params"] = params
        if data is not None:
            kwargs["data"] = data
        response = call(url, **kwargs)
        last = response
        status = int(getattr(response, "status_code", 0) or 0)
        if status not in {429, 500, 502, 503, 504}:
            return response
        if attempt + 1 >= attempts:
            break
        time.sleep(_retry_after_seconds(response, attempt))
    return last


def _get(session, url: str, *, params=None, attempts: int = 5, pace_seconds: float = 1.25):
    return _request(session, "GET", url, params=params, attempts=attempts, pace_seconds=pace_seconds)


def _filter_submission(html: str, page_url: str, facet: str) -> tuple[str, list[tuple[str,str]]]:
    """Build the live Drupal filter POST from its own form fields."""
    soup = BeautifulSoup(html or "", "html.parser")
    country_select = soup.select_one('select[name="job_country[]"]')
    form = country_select.find_parent("form") if country_select else None
    if form is None or clean(form.get("method")).lower() != "post":
        raise RuntimeError("EURAXESS country filter POST form not found")

    action = urljoin(page_url, str(form.get("action") or SEARCH_URL))
    payload: list[tuple[str,str]] = []
    for inp in form.find_all("input"):
        name = clean(inp.get("name"))
        typ = clean(inp.get("type")).lower()
        if not name or typ != "hidden":
            continue
        payload.append((name, clean(inp.get("value"))))

    numeric = clean(facet).split(":",1)[-1]
    payload.append(("job_country[]", numeric))

    offer_select = form.select_one('select[name="offer_type[]"]')
    offer_value = ""
    if offer_select:
        for option in offer_select.find_all("option"):
            value = clean(option.get("value"))
            label = clean(option.get_text(" ", strip=True)).lower()
            if value and ("job" in label or "job" in value.lower()):
                offer_value = value
                break
    if not offer_value:
        raise RuntimeError("EURAXESS job-offer filter option not found")
    payload.append(("offer_type[]", offer_value))

    submit = next(
        (
            node for node in form.find_all(["button", "input"])
            if clean(node.get("type")).lower() == "submit"
            and "apply filters" in (clean(node.get("value")) + " " + clean(node.get_text(" ", strip=True))).lower()
        ),
        None,
    )
    if submit is None or not clean(submit.get("name")):
        raise RuntimeError("EURAXESS Apply filters submit control not found")
    payload.append((clean(submit.get("name")), clean(submit.get("value")) or clean(submit.get_text(" ", strip=True))))
    return action, payload


def parse_listing(html: str, base_url: str = SEARCH_URL) -> list[dict[str,Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    by_id: dict[str,dict[str,Any]] = {}
    for link in soup.find_all("a", href=True):
        href = urljoin(base_url, str(link.get("href") or ""))
        m = JOB_RE.search(href)
        title = clean(link.get_text(" ", strip=True))
        if not m or not title or len(title) < 4:
            continue
        job_id=m.group(1)
        block=link.find_parent(["article","li","div"])
        context=clean(block.get_text(" ", strip=True)) if block else title
        current=by_id.get(job_id)
        item={"id":job_id,"title":title,"url":href,"context":context}
        if current is None or len(title) > len(current.get("title","")):
            by_id[job_id]=item
    return list(by_id.values())


def parse_detail_metadata(html: str) -> dict[str,str]:
    soup=BeautifulSoup(html or "", "html.parser")
    text=clean(soup.get_text(" ", strip=True))
    h1=soup.find("h1")
    title=clean(h1.get_text(" ", strip=True)) if h1 else ""
    if title.lower() in GENERIC_DETAIL_TITLES:
        title=""

    def after(labels: tuple[str,...]) -> str:
        for label in labels:
            m=re.search(rf"{label}\s*:?\s*(.+?)(?=(?:Application Deadline|Research Field|Researcher Profile|Organisation|Organization|Work Location|Work Locations|Posted on|Offer Description|$))", text, re.I)
            if m:
                return clean(m.group(1))
        return ""

    institution=after((r"Organisation",r"Organization"))
    deadline=after((r"Application Deadline",))
    posted=after((r"Posted on",))
    country=""
    m=re.search(r"(?:Country|countries?)\s*:?\s*([A-Za-z .'-]{2,40})", text, re.I)
    if m:
        country=clean(m.group(1))
    return {"title":title,"institution":institution,"deadline":deadline,"posted":posted,"country":country}


def collect(
    *,
    country_codes: tuple[str,...] = TARGET_CODES,
    pages_per_country: int | None = 1,
    max_jobs: int | None = 100,
    enrich_detail: bool = True,
    session=None,
    pace_seconds: float = 1.25,
) -> list[dict[str,Any]]:
    if session is None:
        s=make_session(retries=0)
        no_status_retry=HTTPAdapter(max_retries=0)
        s.mount("https://", no_status_retry)
        s.mount("http://", no_status_retry)
    else:
        s=session

    first=_get(s, SEARCH_URL, pace_seconds=pace_seconds)
    first.raise_for_status()
    form_html=first.text
    form_url=first.url
    facets=discover_country_facets(form_html)
    items=[]; seen=set()

    for code in country_codes:
        facet=_facet_for_code(facets, code)
        if not facet:
            record_coverage(f"{SOURCE_KEY}:{code}","country_facet_missing")
            continue
        try:
            action, payload=_filter_submission(form_html, form_url, facet)
            filtered=_request(s, "POST", action, data=payload, pace_seconds=pace_seconds)
            filtered.raise_for_status()
        except Exception as exc:
            record_coverage(
                f"{SOURCE_KEY}:{code}", "request_failed",
                pages=0, records=0, error=f"{type(exc).__name__}: {exc}",
            )
            continue

        form_html=filtered.text
        form_url=filtered.url
        next_url=next_listing_url(filtered.text, filtered.url)
        first_response=filtered

        def fetch(page):
            nonlocal next_url, first_response
            if first_response is not None:
                r=first_response
                first_response=None
            else:
                if not next_url:
                    return [], None, False
                r=_get(s, next_url, pace_seconds=pace_seconds)
                r.raise_for_status()
            batch=parse_listing(r.text,r.url)
            next_url=next_listing_url(r.text,r.url)
            return batch, None, bool(next_url)

        try:
            batch=paginate(
                fetch,
                source=f"{SOURCE_KEY}:{code}",
                max_jobs=max_jobs,
                max_pages=pages_per_country,
            )
        except Exception:
            continue
        for item in batch:
            if item["id"] not in seen:
                seen.add(item["id"])
                items.append((item,code,facet))
                if reached(items,max_jobs): break
        if reached(items,max_jobs):
            record_coverage(SOURCE_KEY,"configured_record_limit")
            break

    records=[]
    for item, code, facet in items[:max_jobs]:
        detail_text=None
        detail_status="NOT_ATTEMPTED"
        failure=None
        meta={}
        if enrich_detail:
            try:
                rr=_get(s, item["url"], pace_seconds=pace_seconds)
                if rr.status_code == 404:
                    detail_status="UNAVAILABLE"
                    failure="HTTP 404"
                else:
                    rr.raise_for_status()
                    meta=parse_detail_metadata(rr.text)
                    from .common import html_to_text
                    detail_text=html_to_text(rr.text)
                    detail_status="FULL" if len(detail_text)>=200 else ("PARTIAL" if detail_text else "UNAVAILABLE")
            except Exception as exc:
                detail_status="FETCH_FAILED"
                failure=f"{type(exc).__name__}: {exc}"
        country_name=CODE_TO_COUNTRY_NAME.get(code)
        records.append(make_record(
            source_key=SOURCE_KEY, source_kind="SHARED_AGGREGATOR", provider=PROVIDER,
            source_job_id=item["id"], listing_url=SEARCH_URL, detail_url=item["url"],
            title=meta.get("title") or item["title"], institution=meta.get("institution") or None,
            country_code=code, country_name=country_name,
            posted_text=meta.get("posted") or None, deadline_text=meta.get("deadline") or None,
            full_jd=detail_text, detail_status=detail_status, detail_failure_reason=failure,
            source_language="en", source_status="UNKNOWN",
            raw_extra={
                "listing_context":item.get("context",""),
                "requested_country_code":code,
                "country_facet":facet,
                "filter_transport":"POST_FORM",
            },
        ))
    return records
