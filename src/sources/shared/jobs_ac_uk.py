from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .pagination import paginate, reached, record_coverage
from .common import CODE_TO_COUNTRY_NAME, clean, html_to_text, infer_country_code, make_record, make_session

SOURCE_KEY="jobs_ac_uk"
PROVIDER="jobs.ac.uk"
SEARCH_URL="https://www.jobs.ac.uk/search/"
JOB_RE=re.compile(r"/job/([A-Za-z0-9]+)/[^?#]*",re.I)
DEFAULT_KEYWORDS=(
    "exercise physiology","physical activity","sport science","exercise neuroscience",
    "neuroscience","brain health","psychophysiology","stress","cognition",
)
DATE_RE=r"[0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}(?:\s+[0-9]{4})?"
LABELS=("Location","Salary","Hours","Contract Type","Placed On","Placed on","Date Placed","Closes","Expires","Job Ref")


def _strip_ordinal_date(value: str | None) -> str:
    return re.sub(r"\b([0-9]{1,2})(?:st|nd|rd|th)\b", r"\1", clean(value), flags=re.I)


def _bounded_label(text: str, label: str) -> str:
    stop="|".join(re.escape(x) for x in LABELS if x.lower()!=label.lower())
    m=re.search(rf"\b{re.escape(label)}\b\s*:?\s*(.+?)(?=\b(?:{stop})\b\s*:?|$)", text or "", re.I)
    return clean(m.group(1)) if m else ""


def _jsonld_jobposting(html: str) -> dict[str,Any]:
    soup=BeautifulSoup(html or "","html.parser")
    def walk(value: Any):
        if isinstance(value,dict):
            kind=value.get("@type")
            kinds=kind if isinstance(kind,list) else [kind]
            if any(str(x).lower()=="jobposting" for x in kinds if x):
                return value
            for child in value.values():
                found=walk(child)
                if found: return found
        elif isinstance(value,list):
            for child in value:
                found=walk(child)
                if found: return found
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


def _jsonld_location(obj: dict[str,Any]) -> tuple[str,str]:
    locations=obj.get("jobLocation") if obj else None
    if not isinstance(locations,list):
        locations=[locations] if locations else []
    locality=""; country=""
    for loc in locations:
        if not isinstance(loc,dict): continue
        address=loc.get("address") or {}
        if not isinstance(address,dict): continue
        locality=locality or clean(address.get("addressLocality") or address.get("addressRegion"))
        raw_country=address.get("addressCountry")
        if isinstance(raw_country,dict): raw_country=raw_country.get("name") or raw_country.get("@id")
        country=country or clean(raw_country)
    return locality,country


def parse_search(html: str, base_url: str = SEARCH_URL) -> list[dict[str,Any]]:
    soup=BeautifulSoup(html or "","html.parser")
    by_id={}
    for a in soup.find_all("a",href=True):
        href=urljoin(base_url,str(a.get("href") or ""))
        m=JOB_RE.search(href)
        title=clean(a.get_text(" ",strip=True))
        if not m or not title:
            continue
        job_id=m.group(1)
        block=a.find_parent(["article","li","div"])
        context=clean(block.get_text(" ",strip=True)) if block else title
        item=by_id.setdefault(job_id,{
            "id":job_id,"title":title,"url":href,"context":context,
            "location":_bounded_label(context,"Location"),
            "posted":_strip_ordinal_date(_bounded_label(context,"Date Placed") or _bounded_label(context,"Placed on")),
            "deadline":_strip_ordinal_date(_bounded_label(context,"Closes") or _bounded_label(context,"Expires")),
        })
        if len(title)>len(item["title"]):
            item["title"]=title
    return list(by_id.values())


def parse_detail(html: str, fallback_title: str="") -> dict[str,str]:
    soup=BeautifulSoup(html or "","html.parser")
    text=html_to_text(html)
    h1=soup.find("h1")
    title=clean(h1.get_text(" ",strip=True)) if h1 else fallback_title
    obj=_jsonld_jobposting(html)
    locality,country=_jsonld_location(obj)

    # jobs.ac.uk renders metadata as a compact labelled header before the JD. Keep
    # extraction bounded by the next known label rather than applying a free-running
    # regex to the complete description.
    header=soup.find("h1")
    header_root=header.find_parent(["article","main","div"]) if header else None
    header_text=clean(header_root.get_text(" ",strip=True)) if header_root else text[:5000]
    location=locality or _bounded_label(header_text,"Location") or _bounded_label(text[:5000],"Location")
    salary=_bounded_label(header_text,"Salary") or _bounded_label(text[:5000],"Salary")
    deadline=_strip_ordinal_date(_bounded_label(header_text,"Closes") or _bounded_label(header_text,"Expires") or _bounded_label(text[:5000],"Closes") or _bounded_label(text[:5000],"Expires"))
    posted=_strip_ordinal_date(_bounded_label(header_text,"Placed On") or _bounded_label(header_text,"Date Placed") or _bounded_label(text[:5000],"Placed On") or _bounded_label(text[:5000],"Date Placed"))

    institution=""
    org=obj.get("hiringOrganization") if obj else None
    if isinstance(org,dict): institution=clean(org.get("name"))
    elif org: institution=clean(org)
    if not institution:
        for selector in ("[class*='employer']","[class*='company']","h3"):
            node=soup.select_one(selector)
            if node:
                institution=clean(node.get_text(" ",strip=True)); break
    return {
        "title":title,"location":location,"country":country,"salary":salary,
        "deadline":deadline,"posted":posted,"institution":institution,"description":text,
    }


def collect(
    *, keywords: tuple[str,...] = DEFAULT_KEYWORDS, pages_per_query: int | None = 1,
    max_jobs: int | None = 100, enrich_detail: bool = True, session=None,
) -> list[dict[str,Any]]:
    s=session or make_session()
    candidates=[]; seen=set()
    for keyword in keywords:
        def fetch(page):
            params={"keywords":keyword,"location":"","pageSize":25,"sortOrder":2,"startIndex":page*25+1}
            r=s.get(SEARCH_URL,params=params,timeout=(10,45),allow_redirects=True)
            r.raise_for_status()
            return parse_search(r.text,r.url), None, None
        try:
            batch=paginate(fetch,source=f"{SOURCE_KEY}:{keyword}",max_jobs=max_jobs,max_pages=pages_per_query)
        except Exception:
            continue
        for item in batch:
            if item["id"] not in seen:
                seen.add(item["id"])
                item["keyword"]=keyword
                candidates.append(item)
                if reached(candidates,max_jobs): break
        if reached(candidates,max_jobs):
            record_coverage(SOURCE_KEY,"configured_record_limit")
            break

    records=[]
    for item in candidates[:max_jobs]:
        parsed={}; detail=None; detail_status="NOT_ATTEMPTED"; failure=None
        if enrich_detail:
            try:
                r=s.get(item["url"],timeout=(10,45),allow_redirects=True)
                if r.status_code==404:
                    detail_status="UNAVAILABLE"; failure="HTTP 404"
                else:
                    r.raise_for_status()
                    parsed=parse_detail(r.text,item["title"])
                    detail=parsed.get("description") or ""
                    detail_status="FULL" if len(detail)>=200 else ("PARTIAL" if detail else "UNAVAILABLE")
            except Exception as exc:
                detail_status="FETCH_FAILED"; failure=f"{type(exc).__name__}: {exc}"
        location=parsed.get("location") or item.get("location") or ""
        country_name=parsed.get("country") or ""
        code=infer_country_code(country_name, " ".join(filter(None,[location,country_name,parsed.get("institution") or ""])))
        cname=CODE_TO_COUNTRY_NAME.get(code) if code else (country_name or None)
        rec=make_record(
            source_key=SOURCE_KEY,source_kind="SHARED_AGGREGATOR",provider=PROVIDER,
            source_job_id=item["id"],listing_url=SEARCH_URL,detail_url=item["url"],
            title=parsed.get("title") or item["title"],institution=parsed.get("institution") or None,
            country_code=code,country_name=cname,city=location or None,
            posted_text=parsed.get("posted") or item.get("posted") or None,
            deadline_text=parsed.get("deadline") or item.get("deadline") or None,
            full_jd=detail,detail_status=detail_status,detail_failure_reason=failure,
            source_language="en",source_status="UNKNOWN",
            raw_extra={"search_keyword":item.get("keyword"),"listing_context":item.get("context",""),"salary_text":parsed.get("salary"),"country_evidence":country_name or None},
        )
        if parsed.get("salary"):
            rec["contract"]["salary"]["raw_text"]=parsed["salary"]
            rec["contract"]["salary"]["currency"]="GBP" if "£" in parsed["salary"] else None
        records.append(rec)
    return records
