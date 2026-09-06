from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from src.sources.shared.pagination import html_pages, paginate
from src.sources.shared.common import clean, fetch_detail_text, make_record, make_session


@dataclass(frozen=True)
class PageUpTenant:
    key: str
    provider: str
    listing_url: str
    country_code: str = "AU"
    country_name: str = "Australia"


TENANTS: dict[str, PageUpTenant] = {
    "monash": PageUpTenant("monash", "Monash University", "https://careers.pageuppeople.com/513/ind/en/listing/"),
    "deakin": PageUpTenant("deakin", "Deakin University", "https://careers.pageuppeople.com/949/cw/en/listing/"),
    "unsw": PageUpTenant("unsw", "UNSW Sydney", "https://careers.pageuppeople.com/841/cw/en/listing/"),
}


def parse_listing(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a.get("href") or ""))
        m = re.search(r"/(?:job|jobs)/(\d+)(?:/|$)", href, re.I)
        if not m or m.group(1) in seen:
            continue
        title = clean(a.get_text(" ", strip=True))
        if len(title) < 5 or title.lower() in {"read more", "apply now", "back to search results"}:
            continue
        block = a.find_parent("tr") or a.find_parent(["article", "li", "div"]) or a.parent
        context = clean(block.get_text(" | ", strip=True)) if block else title
        deadline_m = re.search(r"(?:Closes|Applications Close|Application close)\s*:?\s*([^|]+)", context, re.I)
        location_m = re.search(r"(?:Location|Campus)\s*:?\s*([^|]+)", context, re.I)
        seen.add(m.group(1))
        out.append({
            "id": m.group(1),
            "title": title,
            "url": href,
            "deadline": clean(deadline_m.group(1)) if deadline_m else "",
            "city": clean(location_m.group(1)) if location_m else "",
            "context": context,
        })
    return out


def _page_number(url: str) -> int:
    raw = (parse_qs(urlparse(url).query).get("page") or ["1"])[0]
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def monash_next_listing_url(html: str, current_url: str) -> str | None:
    """Return only a real forward Monash listing page.

    Monash PageUp has historically exposed generic ``More Jobs`` links. A link
    back to the listing root/self must not be interpreted as pagination because
    that replays already-seen jobs and produces ``repeated_page``. The current
    portal uses ``?page=N&page-items=20``; require an explicit page number that
    advances beyond the current page and stays on the same listing path/origin.
    """
    current = urlparse(current_url)
    current_page = _page_number(current_url)
    candidates: list[tuple[int, str]] = []
    soup = BeautifulSoup(html or "", "html.parser")
    for a in soup.find_all("a", href=True):
        label = " ".join([
            a.get_text(" ", strip=True),
            str(a.get("aria-label") or ""),
            str(a.get("title") or ""),
        ]).strip().lower()
        rel = a.get("rel") or []
        if "next" not in rel and not re.search(r"\bmore jobs\b|\bnext\b|^[›»>]$", label):
            continue
        href = str(a.get("href") or "")
        if href.startswith(("#", "javascript:")):
            continue
        candidate = urljoin(current_url, href)
        parsed = urlparse(candidate)
        if parsed.netloc != current.netloc or parsed.path.rstrip("/") != current.path.rstrip("/"):
            continue
        query = parse_qs(parsed.query)
        if "page" not in query:
            continue
        page = _page_number(candidate)
        if page <= current_page:
            continue
        candidates.append((page, candidate))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _collect_monash_pages(session, tenant: PageUpTenant, *, max_jobs: int | None) -> list[dict[str, Any]]:
    current = tenant.listing_url
    visited: set[str] = set()

    def fetch(_page):
        nonlocal current
        if current in visited:
            raise RuntimeError("Pagination URL repeated: " + current)
        visited.add(current)
        response = session.get(current, timeout=(10, 45), allow_redirects=True)
        response.raise_for_status()
        items = parse_listing(response.text, response.url)
        next_url = monash_next_listing_url(response.text, response.url)
        current = next_url or ""
        return items, None, bool(next_url)

    return paginate(fetch, source=tenant.listing_url, max_jobs=max_jobs)


def collect(*, tenant_key: str, max_jobs: int | None = 100, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    if tenant_key not in TENANTS:
        raise KeyError(f"Unknown PageUp tenant: {tenant_key}")
    tenant = TENANTS[tenant_key]
    s = session or make_session()
    if tenant.key == "monash":
        candidates = _collect_monash_pages(s, tenant, max_jobs=max_jobs)
    else:
        candidates = html_pages(s, tenant.listing_url, parse_listing, max_jobs=max_jobs)
    out: list[dict[str, Any]] = []
    for item in candidates:
        detail = None
        status = "NOT_ATTEMPTED"
        failure = None
        if enrich_detail:
            try:
                detail, status = fetch_detail_text(item["url"], s)
            except Exception as exc:
                status = "FETCH_FAILED"
                failure = f"{type(exc).__name__}: {exc}"
        out.append(
            make_record(
                source_key=f"pageup_{tenant.key}",
                source_kind="ATS",
                provider=tenant.provider,
                source_job_id=item["id"],
                listing_url=tenant.listing_url,
                detail_url=item["url"],
                title=item["title"],
                institution=tenant.provider,
                country_code=tenant.country_code,
                country_name=tenant.country_name,
                city=item.get("city") or None,
                deadline_text=item.get("deadline") or None,
                full_jd=detail,
                detail_status=status,
                detail_failure_reason=failure,
                source_language="en",
                source_status="UNKNOWN",
                raw_extra={"tenant": tenant.key, "listing_context": item.get("context", "")},
            )
        )
    return out
