from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from .pagination import capture_coverage, next_listing_url, paginate, reached, record_coverage
from .common import CODE_TO_COUNTRY_NAME, clean, infer_country_code, make_record, make_session

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
    """Return EURAXESS country labels mapped to stable facet values."""
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


def discover_offer_type_facet(html: str) -> str | None:
    """Discover the current Job Offer facet from the live filter form."""
    soup = BeautifulSoup(html or "", "html.parser")
    select = soup.select_one('select[name="offer_type[]"]')
    if select is None:
        return None
    for option in select.find_all("option"):
        value = clean(option.get("value"))
        label = clean(option.get_text(" ", strip=True)).lower()
        if not value or ("job" not in label and "job" not in value.lower()):
            continue
        return value if value.startswith("offer_type:") else f"offer_type:{value}"
    return None


def _facet_for_code(facets: dict[str, str], code: str) -> str | None:
    labels = COUNTRY_LABEL_ALIASES.get(code) or (CODE_TO_COUNTRY_NAME.get(code) or "",)
    for label in labels:
        facet = facets.get(clean(label).lower())
        if facet:
            return facet
    return None


def _filter_endpoint(html: str, page_url: str) -> str:
    """Use the live form action as the search endpoint without depending on POST transport."""
    soup = BeautifulSoup(html or "", "html.parser")
    country_select = soup.select_one('select[name="job_country[]"]')
    form = country_select.find_parent("form") if country_select else None
    return urljoin(page_url, str(form.get("action") or SEARCH_URL)) if form else page_url


def _filter_params(country_facet: str, offer_facet: str) -> list[tuple[str,str]]:
    return [("f[0]", country_facet), ("f[1]", offer_facet)]


def _url_has_facets(url: str, required_facets: tuple[str,...]) -> bool:
    values = [value for key, value in parse_qsl(urlparse(url).query, keep_blank_values=True) if key.startswith("f[")]
    return all(facet in values for facet in required_facets)


def _assert_filtered_url(url: str, country_facet: str, offer_facet: str) -> None:
    if not _url_has_facets(url, (country_facet, offer_facet)):
        raise RuntimeError(
            "EURAXESS filtered navigation lost active facets: "
            f"country={country_facet}, offer={offer_facet}, url={url}"
        )


def _selected_option_values(html: str, select_name: str) -> set[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    select = soup.select_one(f'select[name="{select_name}"]')
    if select is None:
        return set()
    return {
        clean(option.get("value"))
        for option in select.find_all("option")
        if option.has_attr("selected") and clean(option.get("value"))
    }


def _assert_active_filter_response(response: Any, country_facet: str, offer_facet: str) -> str | None:
    """Reject HTTP-200 pages where EURAXESS silently ignored the requested facets."""
    _assert_filtered_url(response.url, country_facet, offer_facet)
    country_value = country_facet.split(":", 1)[-1]
    offer_value = offer_facet.split(":", 1)[-1]
    selected_countries = _selected_option_values(response.text, "job_country[]")
    selected_offers = _selected_option_values(response.text, "offer_type[]")
    if country_value not in selected_countries and country_facet not in selected_countries:
        raise RuntimeError(
            "EURAXESS response URL retained facets but rendered country filter is inactive: "
            f"country={country_facet}, url={response.url}"
        )
    if offer_value not in selected_offers and offer_facet not in selected_offers:
        raise RuntimeError(
            "EURAXESS response URL retained facets but rendered offer filter is inactive: "
            f"offer={offer_facet}, url={response.url}"
        )
    next_url = next_listing_url(response.text, response.url)
    if next_url and not _url_has_facets(next_url, (country_facet, offer_facet)):
        raise RuntimeError(
            "EURAXESS filtered navigation lost active facets: "
            f"country={country_facet}, offer={offer_facet}, url={next_url}"
        )
    return next_url


def _description_list_value(soup: BeautifulSoup, labels: tuple[str, ...]) -> str:
    wanted = {clean(label).lower() for label in labels}
    for dt in soup.find_all("dt"):
        if clean(dt.get_text(" ", strip=True)).lower() not in wanted:
            continue
        dd = dt.find_next_sibling("dd")
        if dd is not None:
            return clean(dd.get_text(" ", strip=True))
    return ""


def _country_matches_requested(country_name: str, code: str) -> bool:
    normalized = clean(country_name).lower()
    labels = COUNTRY_LABEL_ALIASES.get(code) or (CODE_TO_COUNTRY_NAME.get(code) or "",)
    return any(normalized == clean(label).lower() for label in labels if clean(label))


def _retry_after_seconds(
    response: Any,
    attempt: int,
    *,
    backoff_base_seconds: float = 5.0,
    backoff_cap_seconds: float = 60.0,
    minimum_backoff_seconds: float = 0.0,
) -> float:
    """Return a conservative retry delay while respecting Retry-After.

    Retry-After is treated as a lower bound rather than the only delay. This matters
    for EURAXESS global pagination, where repeated 429s can outlive a short server
    hint and a longer collector-side cooldown is safer than exhausting the retry
    budget quickly.
    """
    exponential = min(
        max(0.0, float(backoff_base_seconds)) * (2.0 ** attempt),
        max(0.0, float(backoff_cap_seconds)),
    )
    minimum = max(0.0, float(minimum_backoff_seconds))
    headers = getattr(response, "headers", {}) or {}
    raw = clean(headers.get("Retry-After"))
    if raw:
        try:
            retry_after = max(0.0, float(raw))
            if minimum > 0:
                return min(max(minimum, exponential, retry_after), float(backoff_cap_seconds))
            return min(retry_after, float(backoff_cap_seconds))
        except ValueError:
            try:
                target = parsedate_to_datetime(raw)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                retry_after = max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
                if minimum > 0:
                    return min(max(minimum, exponential, retry_after), float(backoff_cap_seconds))
                return min(retry_after, float(backoff_cap_seconds))
            except (TypeError, ValueError, OverflowError):
                pass
    return max(minimum, exponential)


def _request(
    session,
    method: str,
    url: str,
    *,
    params=None,
    data=None,
    attempts: int = 5,
    pace_seconds: float = 1.25,
    backoff_base_seconds: float = 5.0,
    backoff_cap_seconds: float = 60.0,
    minimum_backoff_seconds: float = 0.0,
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
        time.sleep(
            _retry_after_seconds(
                response,
                attempt,
                backoff_base_seconds=backoff_base_seconds,
                backoff_cap_seconds=backoff_cap_seconds,
                minimum_backoff_seconds=minimum_backoff_seconds,
            )
        )
    return last


def _get(
    session,
    url: str,
    *,
    params=None,
    attempts: int = 5,
    pace_seconds: float = 1.25,
    backoff_base_seconds: float = 5.0,
    backoff_cap_seconds: float = 60.0,
    minimum_backoff_seconds: float = 0.0,
):
    return _request(
        session,
        "GET",
        url,
        params=params,
        attempts=attempts,
        pace_seconds=pace_seconds,
        backoff_base_seconds=backoff_base_seconds,
        backoff_cap_seconds=backoff_cap_seconds,
        minimum_backoff_seconds=minimum_backoff_seconds,
    )


def _listing_card_metadata(link) -> tuple[str, str, str | None, str]:
    card = link.find_parent("div", id="job-teaser-content")
    labels: list[str] = []
    if card is not None:
        labels = [
            clean(node.get_text(" ", strip=True))
            for node in card.select(".ecl-content-block__label-container .ecl-label")
            if clean(node.get_text(" ", strip=True))
        ]
    offer_type = labels[0].upper() if labels else ""
    country_name = labels[1] if len(labels) > 1 else ""
    country_code = infer_country_code(country_name) if country_name else None
    block = card or link.find_parent(["article", "li", "div"])
    context = clean(block.get_text(" ", strip=True)) if block else clean(link.get_text(" ", strip=True))
    return offer_type, country_name, country_code, context


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
        offer_type, country_name, country_code, context = _listing_card_metadata(link)
        current=by_id.get(job_id)
        item={
            "id":job_id,
            "title":title,
            "url":href,
            "context":context,
            "offer_type":offer_type,
            "listing_country_name":country_name,
            "listing_country_code":country_code,
        }
        if current is None or len(title) > len(current.get("title","")):
            by_id[job_id]=item
    return list(by_id.values())


def _replay_coverage(events: list[dict[str, Any]]) -> None:
    for event in events:
        details = {
            key: value
            for key, value in event.items()
            if key not in {"source", "stop_reason", "complete"}
        }
        record_coverage(
            event["source"],
            event["stop_reason"],
            complete=bool(event.get("complete")),
            **details,
        )


def _preflight_country_filters(
    session,
    *,
    country_codes: tuple[str, ...],
    facets: dict[str, str],
    offer_facet: str,
    filter_endpoint: str,
    pace_seconds: float,
) -> dict[str, tuple[Any, str]]:
    responses: dict[str, tuple[Any, str]] = {}
    for code in country_codes:
        facet = _facet_for_code(facets, code)
        if not facet:
            raise RuntimeError(f"EURAXESS country facet missing for {code}")
        filtered = _get(
            session,
            filter_endpoint,
            params=_filter_params(facet, offer_facet),
            pace_seconds=pace_seconds,
        )
        filtered.raise_for_status()
        _assert_active_filter_response(filtered, facet, offer_facet)
        responses[code] = (filtered, facet)
    return responses


def _increment_euraxess_page(url: str) -> str | None:
    """Advance EURAXESS' zero-based page query when its rendered Next link resets to self."""
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    page_index = None
    current_page = 0
    for index, (key, value) in enumerate(pairs):
        if key != "page":
            continue
        try:
            current_page = int(value)
        except (TypeError, ValueError):
            return None
        page_index = index
        break
    next_page = current_page + 1
    if page_index is None:
        pairs.append(("page", str(next_page)))
    else:
        pairs[page_index] = ("page", str(next_page))
    return urlunparse(parsed._replace(query=urlencode(pairs, doseq=True)))


def _collect_global_fallback(
    session,
    *,
    country_codes: tuple[str, ...],
    pages_per_country: int | None,
    max_jobs: int | None,
    pace_seconds: float,
) -> tuple[list[dict[str, Any]], bool]:
    """Scan the global listing when country facets are unreliable.

    EURAXESS exposes offer type and country as structured labels on each listing card,
    so non-target countries are discarded before detail enrichment.
    """
    target_codes = set(country_codes)
    page_limit = None
    if pages_per_country is not None:
        page_limit = max(1, int(pages_per_country) * max(1, len(country_codes)))

    current_url = SEARCH_URL
    visited: set[str] = set()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    global_seen_ids: set[str] = set()
    first_page_ids: set[str] = set()
    pages = 0
    reason = "unknown"
    complete = False
    error = None
    global_rows_seen = 0
    unresolved_country_rows = 0
    semantic_duplicate_retries = 0

    while True:
        if current_url in visited:
            reason = "repeated_page_url"
            error = f"Repeated global pagination URL: {current_url}"
            break
        visited.add(current_url)
        try:
            response = _get(
                session,
                current_url,
                attempts=8,
                pace_seconds=max(pace_seconds, 2.5),
                backoff_base_seconds=15.0,
                backoff_cap_seconds=180.0,
                minimum_backoff_seconds=15.0,
            )
            response.raise_for_status()
        except Exception as exc:
            reason = "request_failed"
            error = f"{type(exc).__name__}: {exc}"
            break

        pages += 1
        batch = parse_listing(response.text, response.url)
        next_url = next_listing_url(response.text, response.url)

        if not batch:
            reason = "empty_page"
            complete = next_url is None
            break

        batch_ids = {str(item["id"]) for item in batch}
        if not first_page_ids:
            first_page_ids = set(batch_ids)
        elif batch_ids and batch_ids.issubset(global_seen_ids):
            original_batch_ids = set(batch_ids)
            recovered_duplicate = False
            terminal_after_retry = False
            for retry_index in range(2):
                semantic_duplicate_retries += 1
                time.sleep(5.0 * (retry_index + 1))
                try:
                    retry_response = _get(
                        session,
                        current_url,
                        attempts=4,
                        pace_seconds=max(pace_seconds, 2.5),
                        backoff_base_seconds=15.0,
                        backoff_cap_seconds=180.0,
                        minimum_backoff_seconds=15.0,
                    )
                    retry_response.raise_for_status()
                except Exception:
                    continue
                retry_batch = parse_listing(retry_response.text, retry_response.url)
                retry_next_url = next_listing_url(retry_response.text, retry_response.url)
                if not retry_batch:
                    if retry_next_url is None:
                        reason = "last_page_after_retry"
                        complete = True
                        terminal_after_retry = True
                        break
                    continue
                retry_ids = {str(item["id"]) for item in retry_batch}
                if retry_ids and not retry_ids.issubset(global_seen_ids):
                    response = retry_response
                    batch = retry_batch
                    batch_ids = retry_ids
                    next_url = retry_next_url
                    recovered_duplicate = True
                    break
            if terminal_after_retry:
                break
            if not recovered_duplicate:
                if pages >= 3 and original_batch_ids == first_page_ids:
                    reason = "last_page_reset"
                    complete = True
                    break
                reason = "repeated_page_content"
                error = f"EURAXESS global pagination returned no new listing IDs at {response.url}"
                break

        global_rows_seen += len(batch)
        global_seen_ids.update(batch_ids)

        for item in batch:
            offer_type = clean(item.get("offer_type")).upper()
            if offer_type and offer_type != "JOB":
                continue

            listing_name = clean(item.get("listing_country_name"))
            listing_code = item.get("listing_country_code")
            if listing_name:
                matched_target = next(
                    (
                        code for code in country_codes
                        if _country_matches_requested(listing_name, code)
                    ),
                    None,
                )
                if matched_target is None:
                    continue
                listing_code = matched_target
                item["listing_country_code"] = matched_target
            elif listing_code not in target_codes:
                listing_code = None

            if listing_code is None:
                unresolved_country_rows += 1
            job_id = str(item["id"])
            if job_id in seen:
                continue
            seen.add(job_id)
            items.append(item)
            if reached(items, max_jobs):
                break

        if reached(items, max_jobs):
            reason = "configured_record_limit"
            break
        if not next_url:
            reason = "last_page"
            complete = True
            break
        if page_limit is not None and pages >= page_limit:
            reason = "configured_page_limit"
            break
        if next_url in visited:
            advanced = _increment_euraxess_page(response.url)
            if advanced and advanced not in visited:
                next_url = advanced
            else:
                reason = "repeated_page_url"
                error = f"Repeated global pagination URL: {next_url}"
                break
        current_url = next_url

    record_coverage(
        f"{SOURCE_KEY}:global_fallback",
        reason,
        complete=complete,
        pages=pages,
        records=len(items),
        global_rows_seen=global_rows_seen,
        unresolved_country_rows=unresolved_country_rows,
        semantic_duplicate_retries=semantic_duplicate_retries,
        error=error,
    )
    return items, complete


def parse_detail_metadata(html: str) -> dict[str,str]:
    soup=BeautifulSoup(html or "", "html.parser")
    text=clean(soup.get_text(" ", strip=True))
    h1=soup.find("h1")
    title=clean(h1.get_text(" ", strip=True)) if h1 else ""
    if title.lower() in GENERIC_DETAIL_TITLES:
        title=""

    institution=_description_list_value(
        soup,
        ("Organisation/Company", "Organisation", "Organization", "Company/Institute"),
    )
    deadline=_description_list_value(soup, ("Application Deadline",))
    country=_description_list_value(soup, ("Country",))
    posted=""
    posted_match=re.search(
        r"Posted on\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})",
        text,
        re.I,
    )
    if posted_match:
        posted=clean(posted_match.group(1))
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
    offer_facet=discover_offer_type_facet(form_html)
    filter_endpoint=_filter_endpoint(form_html, form_url)

    items: list[tuple[dict[str, Any], str | None, str | None, str, str | None]] = []
    untrusted_item_ids: set[str] = set()
    fallback_reason: str | None = None

    preflight: dict[str, tuple[Any, str]] = {}
    if not offer_facet:
        fallback_reason = "EURAXESS Job Offer facet missing; using global listing labels"
    else:
        try:
            preflight = _preflight_country_filters(
                s,
                country_codes=country_codes,
                facets=facets,
                offer_facet=offer_facet,
                filter_endpoint=filter_endpoint,
                pace_seconds=pace_seconds,
            )
        except Exception as exc:
            fallback_reason = f"{type(exc).__name__}: {exc}"

    if fallback_reason is None:
        filtered_items: list[tuple[dict[str, Any], str | None, str | None, str, str | None]] = []
        seen: set[str] = set()
        result_sets: dict[str, frozenset[str]] = {}

        with capture_coverage() as filtered_coverage:
            for code in country_codes:
                filtered, facet = preflight[code]
                next_url=None
                first_response=filtered

                def fetch(page):
                    nonlocal next_url, first_response
                    if first_response is not None:
                        r=first_response
                        first_response=None
                    else:
                        if not next_url:
                            return [], None, False
                        _assert_filtered_url(next_url, facet, offer_facet)
                        r=_get(s, next_url, pace_seconds=pace_seconds)
                        r.raise_for_status()
                    next_url=_assert_active_filter_response(r, facet, offer_facet)
                    batch=parse_listing(r.text,r.url)
                    return batch, None, bool(next_url)

                try:
                    batch=paginate(
                        fetch,
                        source=f"{SOURCE_KEY}:{code}",
                        max_jobs=max_jobs,
                        max_pages=pages_per_country,
                    )
                except Exception:
                    batch=[]

                ids=frozenset(str(item["id"]) for item in batch)
                if ids:
                    matching_codes=[
                        previous for previous, previous_ids in result_sets.items()
                        if previous_ids == ids
                    ]
                    if matching_codes:
                        untrusted_item_ids.update(ids)
                        record_coverage(
                            f"{SOURCE_KEY}:{code}",
                            "identical_country_result_set",
                            complete=False,
                            records=len(ids),
                            compared_to=",".join(matching_codes),
                        )
                    result_sets[code]=ids

                for item in batch:
                    if item["id"] not in seen:
                        seen.add(item["id"])
                        filtered_items.append((item, code, facet, "GET_FACET", None))
                        if reached(filtered_items,max_jobs):
                            break
                if reached(filtered_items,max_jobs):
                    record_coverage(SOURCE_KEY,"configured_record_limit")
                    break

        unexpected_incomplete = [
            event for event in filtered_coverage
            if not event.get("complete")
            and event.get("stop_reason") not in {"configured_page_limit", "configured_record_limit"}
        ]
        if unexpected_incomplete:
            first_bad = unexpected_incomplete[0]
            fallback_reason = (
                f"{first_bad.get('source')}:{first_bad.get('stop_reason')}"
                + (f" ({first_bad.get('error')})" if first_bad.get("error") else "")
            )
        else:
            _replay_coverage(filtered_coverage)
            items=filtered_items

    if fallback_reason is not None:
        fallback_items, fallback_complete = _collect_global_fallback(
            s,
            country_codes=country_codes,
            pages_per_country=pages_per_country,
            max_jobs=max_jobs,
            pace_seconds=pace_seconds,
        )
        items=[
            (
                item,
                item.get("listing_country_code"),
                None,
                "GLOBAL_LISTING_FALLBACK",
                fallback_reason,
            )
            for item in fallback_items
        ]
        record_coverage(
            SOURCE_KEY,
            "global_fallback_recovered" if fallback_complete else "global_fallback_partial",
            complete=fallback_complete,
            records=len(items),
            filter_failure=fallback_reason,
        )

    records=[]
    target_codes=set(country_codes)
    for item, code, facet, filter_transport, item_fallback_reason in items[:max_jobs]:
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

        detail_country_name=clean(meta.get("country"))
        detail_country_code=infer_country_code(detail_country_name) if detail_country_name else None

        if code is None:
            if detail_country_code in target_codes:
                code=detail_country_code
            elif detail_country_code is not None:
                continue
            else:
                record_coverage(
                    f"{SOURCE_KEY}:global_fallback",
                    "unresolved_listing_country",
                    complete=False,
                    records=1,
                    source_job_id=str(item["id"]),
                    detail_status=detail_status,
                )
                continue

        detail_country_mismatch=bool(detail_country_name and not _country_matches_requested(detail_country_name, code))
        if detail_country_mismatch:
            untrusted_item_ids.add(str(item["id"]))
            record_coverage(
                f"{SOURCE_KEY}:{code}",
                "detail_country_mismatch",
                complete=False,
                records=1,
                source_job_id=str(item["id"]),
                requested_country_code=code,
                detail_country=detail_country_name,
            )

        if detail_country_name:
            if detail_country_mismatch:
                resolved_country_code=detail_country_code
                resolved_country_name=CODE_TO_COUNTRY_NAME.get(detail_country_code) if detail_country_code else detail_country_name
            else:
                resolved_country_code=detail_country_code or code
                resolved_country_name=CODE_TO_COUNTRY_NAME.get(resolved_country_code) or detail_country_name
        elif str(item["id"]) in untrusted_item_ids:
            resolved_country_code=None
            resolved_country_name=None
        else:
            resolved_country_code=code
            resolved_country_name=CODE_TO_COUNTRY_NAME.get(code)

        if detail_country_mismatch:
            country_validation="DETAIL_MISMATCH"
        elif detail_country_name:
            country_validation="DETAIL_MATCH"
        elif str(item["id"]) in untrusted_item_ids:
            country_validation="UNTRUSTED_IDENTICAL_RESULT_SET"
        elif filter_transport == "GLOBAL_LISTING_FALLBACK":
            country_validation="LISTING_CARD_VALIDATED"
        else:
            country_validation="FILTER_URL_VALIDATED"

        records.append(make_record(
            source_key=SOURCE_KEY, source_kind="SHARED_AGGREGATOR", provider=PROVIDER,
            source_job_id=item["id"], listing_url=SEARCH_URL, detail_url=item["url"],
            title=meta.get("title") or item["title"], institution=meta.get("institution") or None,
            country_code=resolved_country_code, country_name=resolved_country_name,
            posted_text=meta.get("posted") or None, deadline_text=meta.get("deadline") or None,
            full_jd=detail_text, detail_status=detail_status, detail_failure_reason=failure,
            source_language="en", source_status="UNKNOWN",
            raw_extra={
                "listing_context":item.get("context",""),
                "requested_country_code":code,
                "country_facet":facet,
                "offer_type_facet":offer_facet,
                "filter_transport":filter_transport,
                "fallback_reason":item_fallback_reason,
                "listing_offer_type":item.get("offer_type") or None,
                "listing_country":item.get("listing_country_name") or None,
                "listing_country_code":item.get("listing_country_code"),
                "detail_country":detail_country_name or None,
                "detail_country_code":detail_country_code,
                "country_validation":country_validation,
            },
        ))
    return records
