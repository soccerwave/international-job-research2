from __future__ import annotations
import re
from typing import Any
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from .common import clean, fetch_detail_text, make_record, make_session
from .pagination import record_coverage

SOURCE_KEY="dvs"; PROVIDER="Deutsche Vereinigung für Sportwissenschaft"
LISTING_URL="https://www.sportwissenschaft.de/stellenborse/stellenangebote/"


def infer_dvs_country(institution:str,url:str,detail:str|None="")->str|None:
    """Infer country only from explicit source-local evidence.

    The dvs board occasionally carries non-German vacancies, so the board itself is
    not treated as proof of Germany. Domain and textual country signals are enough.
    """
    evidence=" ".join(filter(None,[institution,url,detail or ""]))
    if re.search(r"\b(?:Wien|Vienna|Österreich|Austria)\b|\.at(?:/|$)",evidence,re.I):
        return "AT"
    if re.search(r"\b(?:Schweiz|Switzerland|Suisse)\b|\.ch(?:/|$)",evidence,re.I):
        return "CH"
    if re.search(r"\b(?:Deutschland|Germany)\b|\.de(?:/|$)",evidence,re.I):
        return "DE"
    return None


def parse_listing(html:str,base_url:str=LISTING_URL)->list[dict[str,Any]]:
    soup=BeautifulSoup(html or "","html.parser"); out=[]; seen=set()
    for a in soup.find_all("a",href=True):
        label=clean(a.get_text(" ",strip=True)).lower()
        if "mehr" not in label: continue
        href=urljoin(base_url,str(a.get("href") or ""))
        if href in seen: continue
        seen.add(href)
        block=a.find_parent(["p","div","li","article"]) or a.parent
        lines=[clean(x) for x in block.get_text("\n",strip=True).splitlines() if clean(x)]
        lines=[x for x in lines if "mehr..." not in x.lower() and not x.lower().startswith("bewerbungsschluss")]
        employer=lines[0] if lines else ""
        title=" ".join(lines[1:]) if len(lines)>1 else (lines[0] if lines else "")
        full_block=clean(block.get_text(" ",strip=True))
        m=re.search(r"Bewerbungsschluss:\s*([0-9.]+|nicht angegeben)",full_block,re.I)
        deadline="" if not m or "nicht" in m.group(1).lower() else m.group(1)
        jid=re.search(r"(\d{3,})",href)
        source_id=jid.group(1) if jid else re.sub(r"\W+","-",urlparse(href).path.strip("/"))[-100:] or str(len(out)+1)
        out.append({"id":source_id,"title":title,"institution":employer,"deadline":deadline,"url":href,"context":full_block})
    return out


def collect(*,max_jobs:int|None=60,enrich_detail:bool=True,session=None)->list[dict[str,Any]]:
    s=session or make_session(); r=s.get(LISTING_URL,timeout=(10,45)); r.raise_for_status()
    parsed=parse_listing(r.text,r.url)
    limited=max_jobs is not None and len(parsed)>max_jobs
    items=parsed if max_jobs is None else parsed[:max_jobs]
    record_coverage(
        SOURCE_KEY,
        "configured_record_limit" if limited else "single_page_complete",
        complete=not limited,
        pages=1,
        records=len(items),
        discovered_records=len(parsed),
        configured_record_limit=max_jobs,
    )
    out=[]
    for item in items:
        detail=None; status="NOT_ATTEMPTED"; failure=None
        if enrich_detail:
            try: detail,status=fetch_detail_text(item["url"],s)
            except Exception as exc: status="FETCH_FAILED"; failure=f"{type(exc).__name__}: {exc}"
        code=infer_dvs_country(item["institution"],item["url"],detail)
        country_name={"DE":"Germany","AT":"Austria","CH":"Switzerland"}.get(code)
        out.append(make_record(source_key=SOURCE_KEY,source_kind="THEMATIC_PORTAL",provider=PROVIDER,
          source_job_id=item["id"],listing_url=LISTING_URL,detail_url=item["url"],title=item["title"],
          institution=item["institution"],country_code=code,country_name=country_name,
          deadline_text=item["deadline"] or None,full_jd=detail,detail_status=status,detail_failure_reason=failure,
          source_language="de",source_status="UNKNOWN",raw_extra={"listing_context":item["context"],"country_inference":"explicit_domain_or_text" if code else "unknown"}))
    return out
