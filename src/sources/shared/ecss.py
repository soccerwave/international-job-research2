from __future__ import annotations
import re
from typing import Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .common import clean, fetch_detail_text, infer_country_code, make_record, make_session
from .pagination import record_coverage

SOURCE_KEY="ecss"; PROVIDER="European College of Sport Science"
LISTING_URL="https://www.ecss2006.com/ASP/CONGRESS/TOOLS/BENEFITS/EVSS.asp"


def parse_listing(html: str, base_url: str=LISTING_URL) -> list[dict[str,Any]]:
    soup=BeautifulSoup(html or "","html.parser"); rows=[]
    for tr in soup.find_all("tr"):
        cells=tr.find_all(["td","th"])
        if len(cells)<6: continue
        vals=[clean(c.get_text(" ",strip=True)) for c in cells]
        if "announcing date" in vals[0].lower(): continue
        link=cells[-1].find("a",href=True)
        if not link: continue
        detail=urljoin(base_url,str(link.get("href") or ""))
        m=re.search(r"/(\d+)\.pdf(?:$|\?)",detail,re.I)
        jid=m.group(1) if m else re.sub(r"\W+","-",detail)[-80:]
        rows.append({"id":jid,"announced":vals[0],"deadline":vals[1],"title":vals[2],"institution":vals[3],"country":vals[4],"url":detail})
    return rows


def collect(*, max_jobs:int|None=40, enrich_detail:bool=True, session=None)->list[dict[str,Any]]:
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
        code=infer_country_code(item["country"],item["country"])
        out.append(make_record(source_key=SOURCE_KEY,source_kind="THEMATIC_PORTAL",provider=PROVIDER,
          source_job_id=item["id"],listing_url=LISTING_URL,detail_url=item["url"],title=item["title"],
          institution=item["institution"],country_name=item["country"],country_code=code,
          posted_text=item["announced"],deadline_text=item["deadline"],full_jd=detail,detail_status=status,
          detail_failure_reason=failure,source_language="en",source_status="UNKNOWN",raw_extra={"vacancy_type_prefix":item["title"][:4]}))
    return out
