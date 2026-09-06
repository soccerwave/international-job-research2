from __future__ import annotations
import re
from typing import Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .pagination import paginate, reached, record_coverage
from .common import clean, html_to_text, infer_country_code, make_record, make_session
SOURCE_KEY="fens"; PROVIDER="Federation of European Neuroscience Societies"
BASE="https://www.fens.org"; LISTING_URL=f"{BASE}/careers/job-market"
JOB_RE=re.compile(r"/careers/job-market/job/(\d+)",re.I)


def parse_listing(html:str,base_url:str=BASE)->list[dict[str,Any]]:
    soup=BeautifulSoup(html or "","html.parser"); by_id={}; order=[]
    for a in soup.find_all("a",href=True):
        href=urljoin(base_url,str(a.get("href") or "")); m=JOB_RE.search(href)
        if not m: continue
        title=clean(a.get_text(" ",strip=True))
        if not title: continue
        job_id=m.group(1); block=a.find_parent("tr") or a.find_parent(["article","li","div"])
        context=clean(block.get_text(" | ",strip=True)) if block else title
        current=by_id.get(job_id)
        item={"id":job_id,"title":title,"url":href,"context":context}
        if current is None:
            by_id[job_id]=item; order.append(job_id)
        elif len(title)>len(current.get("title","")):
            by_id[job_id]=item
    return [by_id[job_id] for job_id in order]


def parse_detail(html:str,fallback_title:str="")->dict[str,str]:
    soup=BeautifulSoup(html or "","html.parser"); text=html_to_text(html)
    h1=soup.find("h1"); title=clean(h1.get_text(" ",strip=True)) if h1 else fallback_title
    def field(label:str)->str:
        m=re.search(rf"{label}\s*:?\s*(.*?)(?=(?:Position|Deadline|Employment Start Date|Contract Length|City|Country|Institution|Department|Description|$))",text,re.I)
        return clean(m.group(1)) if m else ""
    return {"title":title,"position":field("Position"),"deadline":field("Deadline"),"city":field("City"),
            "country":field("Country"),"institution":field("Institution"),"department":field("Department"),"description":text}


def collect(*,max_pages: int | None=3,max_jobs: int | None=80,enrich_detail:bool=True,session=None)->list[dict[str,Any]]:
    s=session or make_session()
    def fetch(page):
        url=LISTING_URL if page==1 else f"{LISTING_URL}/page/{page}"
        r=s.get(url,timeout=(10,45))
        if page>1 and getattr(r,"status_code",200)==404:
            return [], None, False
        r.raise_for_status()
        return parse_listing(r.text,r.url), None, None
    candidates=paginate(fetch,source=SOURCE_KEY,max_jobs=max_jobs,max_pages=max_pages,start=1)
    out=[]
    for item in candidates[:max_jobs]:
        parsed={}; detail=None; status="NOT_ATTEMPTED"; failure=None
        if enrich_detail:
            try:
                r=s.get(item["url"],timeout=(10,45)); r.raise_for_status(); parsed=parse_detail(r.text,item["title"])
                detail=parsed.get("description") or ""; status="FULL" if len(detail)>=200 else ("PARTIAL" if detail else "UNAVAILABLE")
            except Exception as exc: status="FETCH_FAILED"; failure=f"{type(exc).__name__}: {exc}"
        country=parsed.get("country") or ""; code=infer_country_code(country,country)
        out.append(make_record(source_key=SOURCE_KEY,source_kind="THEMATIC_PORTAL",provider=PROVIDER,
          source_job_id=item["id"],listing_url=LISTING_URL,detail_url=item["url"],title=parsed.get("title") or item["title"],
          institution=parsed.get("institution") or None,department=parsed.get("department") or None,
          country_name=country or None,country_code=code,city=parsed.get("city") or None,deadline_text=parsed.get("deadline") or None,
          full_jd=detail,detail_status=status,detail_failure_reason=failure,source_language="en",source_status="UNKNOWN",
          raw_extra={"position_text":parsed.get("position"),"listing_context":item.get("context","")}))
    return out
