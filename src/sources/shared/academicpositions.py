from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .pagination import next_listing_url, paginate, reached, record_coverage
from .common import CODE_TO_COUNTRY_NAME, clean, html_to_text, make_record, make_session

SOURCE_KEY = "academicpositions"
PROVIDER = "Academic Positions"
COUNTRY_SLUGS = {
    "NL":"netherlands","DE":"germany","IE":"ireland","GB":"united-kingdom","BE":"belgium",
    "FR":"france","AT":"austria","IT":"italy","PT":"portugal","CZ":"czechia",
    "PL":"poland","LU":"luxembourg","AU":"australia",
}
AD_RE = re.compile(r"/ad/[^?#]+/(\d+)(?:[/?#]|$)", re.I)
JOBS_TOTAL_RE = re.compile(r"\b([\d][\d\s,.]*)\s+jobs?\s+in\b", re.I)
BLOCK_MARKERS=("just a moment...","checking your browser","verify you are human","cf-chl-","cloudflare ray id")


def is_blocked(html: str) -> bool:
    low=(html or "").lower()
    return any(marker in low for marker in BLOCK_MARKERS)


def parse_listing(html: str, base_url: str) -> list[dict[str,Any]]:
    soup=BeautifulSoup(html or "", "html.parser")
    by_id={}
    for a in soup.find_all("a", href=True):
        href=urljoin(base_url,str(a.get("href") or ""))
        m=AD_RE.search(urlparse(href).path)
        label=clean(a.get_text(" ", strip=True))
        if not m or not label:
            continue
        job_id=m.group(1)
        item=by_id.setdefault(job_id,{"id":job_id,"title":label,"urls":[]})
        if href not in item["urls"]:
            item["urls"].append(href)
        if len(label)>len(item["title"]):
            item["title"]=label
    return list(by_id.values())


def parse_advertised_total(html: str) -> int | None:
    """Read the country-result count shown by Academic Positions when present."""
    soup=BeautifulSoup(html or "", "html.parser")
    heading=soup.find(["h1","h2"])
    text=clean(heading.get_text(" ",strip=True)) if heading else ""
    match=JOBS_TOTAL_RE.search(text)
    if not match:
        return None
    digits=re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


def jsonld_jobposting(html: str) -> dict[str,Any]:
    soup=BeautifulSoup(html or "", "html.parser")
    def walk(value: Any):
        if isinstance(value,dict):
            kind=value.get("@type")
            kinds=kind if isinstance(kind,list) else [kind]
            if any(str(x).lower()=="jobposting" for x in kinds if x):
                return value
            for child in value.values():
                found=walk(child)
                if found:
                    return found
        elif isinstance(value,list):
            for child in value:
                found=walk(child)
                if found:
                    return found
        return None
    for node in soup.find_all("script",attrs={"type":re.compile(r"ld\+json",re.I)}):
        raw=node.string or node.get_text() or ""
        try:
            found=walk(json.loads(raw))
        except Exception:
            found=None
        if found:
            return found
    return {}


def parse_detail(html: str, fallback_title: str = "") -> dict[str,Any]:
    if is_blocked(html):
        return {"blocked":True}
    obj=jsonld_jobposting(html)
    soup=BeautifulSoup(html or "", "html.parser")
    title=clean(obj.get("title")) if obj else ""
    if not title:
        h1=soup.find("h1")
        title=clean(h1.get_text(" ",strip=True)) if h1 else fallback_title
    org=obj.get("hiringOrganization") if obj else {}
    institution=clean(org.get("name")) if isinstance(org,dict) else clean(org)
    country=city=region=""
    locations=obj.get("jobLocation") if obj else None
    if not isinstance(locations,list):
        locations=[locations] if locations else []
    for loc in locations:
        if not isinstance(loc,dict):
            continue
        addr=loc.get("address") or {}
        if not isinstance(addr,dict):
            continue
        city=city or clean(addr.get("addressLocality"))
        region=region or clean(addr.get("addressRegion"))
        raw_country=addr.get("addressCountry")
        if isinstance(raw_country,dict):
            raw_country=raw_country.get("name")
        country=country or clean(raw_country)
    description=""
    if obj and obj.get("description"):
        description=clean(BeautifulSoup(str(obj.get("description")),"html.parser").get_text(" ",strip=True))
    if len(description)<200:
        main=soup.find("main") or soup.find("article")
        main_text=clean(main.get_text(" ",strip=True)) if main else ""
        description=main_text if len(main_text)>=200 else html_to_text(html)
    return {
        "blocked":False,"title":title,"institution":institution,"country":country,
        "city":city,"region":region,"posted":clean(obj.get("datePosted"))[:10] if obj else "",
        "deadline":clean(obj.get("validThrough"))[:10] if obj else "",
        "description":description,
    }


def collect(
    *, country_codes: tuple[str,...] = tuple(COUNTRY_SLUGS),
    max_pages_per_country: int | None = 2, max_jobs: int | None = 120,
    enrich_detail: bool = True, session=None,
) -> list[dict[str,Any]]:
    s=session or make_session()
    candidates=[]
    seen=set()
    for code in country_codes:
        slug=COUNTRY_SLUGS.get(code)
        if not slug:
            continue
        base=f"https://academicpositions.com/jobs/country/{slug}"
        def fetch(page):
            r=s.get(base, params={} if page==1 else {"page":page}, timeout=(10,45), allow_redirects=True)
            # Academic Positions returns 404 for a known country route when that country
            # currently has no result page. Treat only the first-page 404 as a clean zero;
            # a later-page 404 is inconsistent with the paginator and remains a failure.
            if r.status_code == 404 and page == 1:
                return [], 0, False
            r.raise_for_status()
            if is_blocked(r.text):
                raise RuntimeError("Academic Positions access challenge")
            items=parse_listing(r.text, r.url)
            total=parse_advertised_total(r.text)
            has_next=next_listing_url(r.text, r.url) is not None
            return items, total, has_next
        try:
            batch=paginate(fetch, source=base, max_jobs=max_jobs, max_pages=max_pages_per_country, start=1)
        except Exception:
            continue  # failure already recorded; other countries must still run
        for item in batch:
            if item["id"] not in seen:
                seen.add(item["id"])
                candidates.append((item,code,base))
                if reached(candidates,max_jobs): break
        if reached(candidates,max_jobs):
            record_coverage(SOURCE_KEY,"configured_record_limit")
            break

    records=[]
    for item, code, listing_url in candidates[:max_jobs]:
        detail=None; detail_status="NOT_ATTEMPTED"; failure=None; detail_url=(item["urls"][0] if item["urls"] else None)
        parsed={}
        if enrich_detail and detail_url:
            urls=sorted(item["urls"],key=lambda u:(0 if urlparse(u).netloc.endswith("academicpositions.com") else 1,u))
            for url in urls:
                try:
                    r=s.get(url,timeout=(10,45),allow_redirects=True)
                    r.raise_for_status()
                    parsed=parse_detail(r.text,item["title"])
                    if parsed.get("blocked"):
                        detail_status="BLOCKED"; failure="Academic Positions access challenge"
                        continue
                    detail=parsed.get("description") or ""
                    detail_status="FULL" if len(detail)>=200 else ("PARTIAL" if detail else "UNAVAILABLE")
                    detail_url=r.url
                    break
                except Exception as exc:
                    detail_status="FETCH_FAILED"; failure=f"{type(exc).__name__}: {exc}"
        records.append(make_record(
            source_key=SOURCE_KEY, source_kind="SHARED_AGGREGATOR", provider=PROVIDER,
            source_job_id=item["id"], listing_url=listing_url, detail_url=detail_url,
            title=parsed.get("title") or item["title"], institution=parsed.get("institution") or None,
            country_code=code, country_name=parsed.get("country") or CODE_TO_COUNTRY_NAME.get(code),
            city=parsed.get("city") or None, region=parsed.get("region") or None,
            posted_text=parsed.get("posted") or None, deadline_text=parsed.get("deadline") or None,
            full_jd=detail, detail_status=detail_status, detail_failure_reason=failure,
            source_language="en", source_status="UNKNOWN",
            raw_extra={"country_slug":COUNTRY_SLUGS.get(code)},
        ))
    return records
