from __future__ import annotations

import json
import re
import time
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
BLOCK_MARKERS=("just a moment...","checking your browser","verify you are human","cf-chl-","cloudflare ray id","enable javascript and cookies to continue")
READER_PREFIX="https://r.jina.ai/http://academicpositions.com"
READER_PAGE_SIZE=30
READER_MIN_INTERVAL_SECONDS=3.2
READER_REGIONAL_PREFIXES=("no","dk","be")
READER_LINK_RE=re.compile(r"https?://academicpositions\.com/(?:[a-z]{2}/)?ad/[^\s)\]>]+/\d+", re.I)
READER_TOTAL_RE=re.compile(r"^Title:\s*([\d][\d\s,.]*)\s+jobs?\s+in\b", re.I|re.M)
READER_TITLE_RE=re.compile(r"^Title:\s*(.*?)\s*-\s*Academic Positions\s*$", re.I|re.M)


def is_blocked(html: str) -> bool:
    low=(html or "").lower()
    return any(marker in low for marker in BLOCK_MARKERS)


def _canonical_academicpositions_url(url: str) -> str:
    parsed=urlparse(url)
    path=parsed.path or "/"
    parts=path.split("/")
    if len(parts)>2 and re.fullmatch(r"[a-z]{2}",parts[1],re.I) and parts[2] in {"ad","jobs"}:
        path="/" + "/".join(parts[2:])
    result="https://academicpositions.com" + path
    if parsed.query:
        result += "?" + parsed.query
    return result


def _reader_source_candidates(url: str, *, allow_regional: bool) -> list[str]:
    canonical=_canonical_academicpositions_url(url)
    parsed=urlparse(canonical)
    candidates=[canonical]
    if allow_regional and (parsed.path.startswith("/jobs/") or parsed.path.startswith("/ad/")):
        for prefix in READER_REGIONAL_PREFIXES:
            alt=f"https://academicpositions.com/{prefix}{parsed.path}"
            if parsed.query:
                alt += "?" + parsed.query
            candidates.append(alt)
    return candidates


def _reader_url(source_url: str) -> str:
    parsed=urlparse(source_url)
    url=READER_PREFIX + (parsed.path or "/")
    if parsed.query:
        url += "?" + parsed.query
    return url


def parse_reader_listing(text: str) -> list[dict[str,Any]]:
    by_id={}
    for raw_url in READER_LINK_RE.findall(text or ""):
        href=_canonical_academicpositions_url(raw_url)
        parsed=urlparse(href)
        m=AD_RE.search(parsed.path)
        if not m:
            continue
        job_id=m.group(1)
        parts=[part for part in parsed.path.split("/") if part]
        slug=parts[-2] if len(parts)>=2 else job_id
        title=clean(slug.replace("-"," "))
        item=by_id.setdefault(job_id,{"id":job_id,"title":title,"urls":[],"transport":"reader"})
        if href not in item["urls"]:
            item["urls"].append(href)
    return list(by_id.values())


def parse_reader_total(text: str) -> int | None:
    match=READER_TOTAL_RE.search(text or "")
    if not match:
        return None
    digits=re.sub(r"\D","",match.group(1))
    return int(digits) if digits else None


def parse_reader_detail(text: str, fallback_title: str = "") -> dict[str,Any]:
    if is_blocked(text):
        return {"blocked":True}
    title_match=READER_TITLE_RE.search(text or "")
    title=clean(title_match.group(1)) if title_match else fallback_title
    marker="Markdown Content:"
    description=(text.split(marker,1)[1] if marker in text else text) or ""
    description=clean(description)
    deadline_match=re.search(r"Closing on:\s*(\d{4}-\d{2}-\d{2})",text or "",re.I)
    return {
        "blocked":False,
        "title":title,
        "institution":"",
        "country":"",
        "city":"",
        "region":"",
        "posted":"",
        "deadline":deadline_match.group(1) if deadline_match else "",
        "description":description,
    }


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
    enrich_detail: bool = True, session=None, reader_session=None,
) -> list[dict[str,Any]]:
    s=session or make_session()
    reader=reader_session or make_session(retries=1,backoff=1.0)
    if hasattr(reader,"headers"):
        reader.headers.update({
            "User-Agent":"Mozilla/5.0 (compatible; academic-job-monitor/1.0)",
            "Accept":"text/plain,text/markdown,*/*",
        })
    reader_pace=0.0 if reader_session is not None else READER_MIN_INTERVAL_SECONDS
    last_reader_at=0.0
    reader_mode=False

    def reader_fetch(source_url: str, *, allow_regional: bool = True) -> tuple[str,str]:
        nonlocal last_reader_at
        errors=[]
        for candidate in _reader_source_candidates(source_url,allow_regional=allow_regional):
            for no_cache in (False,True):
                wait=reader_pace-(time.monotonic()-last_reader_at)
                if wait>0:
                    time.sleep(wait)
                headers={"X-Cache-Tolerance":"3600"}
                if no_cache:
                    headers["X-No-Cache"]="true"
                try:
                    response=reader.get(
                        _reader_url(candidate),
                        headers=headers,
                        timeout=(10,90),
                        allow_redirects=True,
                    )
                    last_reader_at=time.monotonic()
                    response.raise_for_status()
                except Exception as exc:
                    errors.append(f"{candidate}: {type(exc).__name__}: {exc}")
                    continue
                if is_blocked(response.text):
                    errors.append(f"{candidate}: reader challenge")
                    continue
                return response.text,candidate
        raise RuntimeError("Academic Positions reader fallback failed: " + " | ".join(errors[-6:]))

    candidates=[]
    seen=set()
    for code in country_codes:
        slug=COUNTRY_SLUGS.get(code)
        if not slug:
            continue
        base=f"https://academicpositions.com/jobs/country/{slug}"
        def fetch(page):
            nonlocal reader_mode
            source_url=base if page==1 else f"{base}?page={page}"
            if reader_mode:
                text,_=reader_fetch(source_url,allow_regional=True)
                items=parse_reader_listing(text)
                total=parse_reader_total(text)
                return items,total,len(items)>=READER_PAGE_SIZE

            r=s.get(base,params={} if page==1 else {"page":page},timeout=(10,45),allow_redirects=True)
            if r.status_code == 404 and page == 1:
                return [],0,False
            if (r.status_code == 403 and is_blocked(r.text)) or is_blocked(r.text):
                reader_mode=True
                text,_=reader_fetch(source_url,allow_regional=True)
                items=parse_reader_listing(text)
                total=parse_reader_total(text)
                return items,total,len(items)>=READER_PAGE_SIZE
            r.raise_for_status()
            items=parse_listing(r.text,r.url)
            total=parse_advertised_total(r.text)
            has_next=next_listing_url(r.text,r.url) is not None
            return items,total,has_next
        try:
            batch=paginate(fetch,source=base,max_jobs=max_jobs,max_pages=max_pages_per_country,start=1)
        except Exception:
            continue
        for item in batch:
            if item["id"] not in seen:
                seen.add(item["id"])
                candidates.append((item,code,base))
                if reached(candidates,max_jobs):
                    break
        if reached(candidates,max_jobs):
            record_coverage(SOURCE_KEY,"configured_record_limit")
            break

    records=[]
    for item,code,listing_url in candidates[:max_jobs]:
        detail=None
        detail_status="NOT_ATTEMPTED"
        failure=None
        detail_url=(item["urls"][0] if item["urls"] else None)
        parsed={}
        if enrich_detail and detail_url:
            urls=sorted(item["urls"],key=lambda u:(0 if urlparse(u).netloc.endswith("academicpositions.com") else 1,u))
            for url in urls:
                try:
                    if reader_mode or item.get("transport")=="reader":
                        text,_=reader_fetch(url,allow_regional=True)
                        parsed=parse_reader_detail(text,item["title"])
                        detail_url=_canonical_academicpositions_url(url)
                    else:
                        r=s.get(url,timeout=(10,45),allow_redirects=True)
                        if (r.status_code == 403 and is_blocked(r.text)) or is_blocked(r.text):
                            reader_mode=True
                            text,_=reader_fetch(url,allow_regional=True)
                            parsed=parse_reader_detail(text,item["title"])
                            detail_url=_canonical_academicpositions_url(url)
                        else:
                            r.raise_for_status()
                            parsed=parse_detail(r.text,item["title"])
                            detail_url=r.url
                    if parsed.get("blocked"):
                        detail_status="BLOCKED"
                        failure="Academic Positions access challenge"
                        continue
                    detail=parsed.get("description") or ""
                    detail_status="FULL" if len(detail)>=200 else ("PARTIAL" if detail else "UNAVAILABLE")
                    failure=None
                    break
                except Exception as exc:
                    detail_status="FETCH_FAILED"
                    failure=f"{type(exc).__name__}: {exc}"
        records.append(make_record(
            source_key=SOURCE_KEY,source_kind="SHARED_AGGREGATOR",provider=PROVIDER,
            source_job_id=item["id"],listing_url=listing_url,detail_url=detail_url,
            title=parsed.get("title") or item["title"],institution=parsed.get("institution") or None,
            country_code=code,country_name=parsed.get("country") or CODE_TO_COUNTRY_NAME.get(code),
            city=parsed.get("city") or None,region=parsed.get("region") or None,
            posted_text=parsed.get("posted") or None,deadline_text=parsed.get("deadline") or None,
            full_jd=detail,detail_status=detail_status,detail_failure_reason=failure,
            source_language="en",source_status="UNKNOWN",
            raw_extra={
                "country_slug":COUNTRY_SLUGS.get(code),
                "access_transport":item.get("transport") or ("reader" if reader_mode else "direct"),
            },
        ))
    return records