from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.sources.shared.common import clean, fetch_detail_text, make_record, make_session
from src.sources.shared.pagination import html_pages


CNRS_URL = "https://emploi.cnrs.fr/Offres/Recherche.aspx"


def _block_text(anchor) -> str:
    block = anchor.find_parent(["article", "li", "tr", "div"]) or anchor.parent
    return clean(block.get_text(" | ", strip=True)) if block else clean(anchor.get_text(" ", strip=True))


def _legacy_stable_tail_id(url: str) -> str:
    """Preserve the source-record ID contract used by the previous CNRS collector."""
    path = urlparse(url).path.strip("/")
    m = re.search(r"(?:^|/)(\d{4,})(?:/|$)", path)
    if m:
        return m.group(1)
    m = re.search(r"(\d{4,})$", path)
    if m:
        return m.group(1)
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return slug[-120:] or "unknown"


def _is_offer_detail_url(url: str) -> bool:
    """Accept concrete CNRS offer detail pages, independent of role keywords."""
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc.lower() != "emploi.cnrs.fr":
        return False
    return bool(re.search(r"/Offres/[^/]+/[^/]+/Default\.aspx/?$", parsed.path, re.I))


def parse_listing(html: str, base_url: str = CNRS_URL) -> list[dict[str, Any]]:
    """Parse every concrete CNRS offer link without pre-evaluator role filtering."""
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, str(anchor.get("href") or ""))
        if not _is_offer_detail_url(href):
            continue
        source_id = _legacy_stable_tail_id(href)
        if source_id in seen:
            continue
        title = clean(anchor.get_text(" ", strip=True))
        context = _block_text(anchor)
        if not title:
            title = context[:160]
        if not title:
            continue
        seen.add(source_id)
        out.append({"id": source_id, "title": title, "url": href, "context": context})
    return out


def collect(*, max_jobs: int | None = 80, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    s = session or make_session()
    candidates = html_pages(s, CNRS_URL, parse_listing, max_jobs=max_jobs)
    out: list[dict[str, Any]] = []
    for item in candidates:
        detail = None
        detail_status = "NOT_ATTEMPTED"
        failure = None
        if enrich_detail:
            try:
                detail, detail_status = fetch_detail_text(item["url"], s)
            except Exception as exc:
                detail_status = "FETCH_FAILED"
                failure = f"{type(exc).__name__}: {exc}"
        out.append(
            make_record(
                source_key="cnrs_emploi",
                source_kind="CORE_MARKET_PORTAL",
                provider="CNRS Emploi",
                source_job_id=str(item["id"]),
                listing_url=CNRS_URL,
                detail_url=item["url"],
                title=item["title"],
                country_code="FR",
                country_name="France",
                full_jd=detail,
                detail_status=detail_status,
                detail_failure_reason=failure,
                source_language="fr",
                source_status="UNKNOWN",
                raw_extra={"listing_context": item.get("context", "")},
            )
        )
    return out
