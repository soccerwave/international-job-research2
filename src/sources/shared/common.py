from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SCHEMA_VERSION = "VACANCY_SCHEMA_V1.0.0"
CORE_COUNTRIES = {"NL","DE","IE","GB","BE","FR","AU","AT"}
OPPORTUNISTIC_COUNTRIES = {"IT","PT","CZ","PL","LU"}
EXCLUDED_COUNTRIES = {"SE","CA","CH"}

# A FULL status is an evidence claim, not a length claim. These collectors consume
# a known job-detail contract: a structured detail API, a source-specific detail
# page, or (for ECSS) the advertised vacancy PDF. Generic/unregistered HTML remains
# PARTIAL even if it contains thousands of characters.
_SOURCE_SPECIFIC_COMPLETE_DETAIL_KEYS = {
    "academicpositions", "academictransfer", "academics_de", "cnrs_emploi",
    "ecss", "euraxess", "fens", "jobs_ac_uk", "linkedin_mads",
    "uibk", "uniroles_au", "university_vacancies_ie",
}
_SOURCE_SPECIFIC_COMPLETE_DETAIL_PREFIXES = (
    "corehr_", "pageup_", "smartrecruiters_", "successfactors_", "workday_",
)

COUNTRY_NAME_TO_CODE = {
    "netherlands":"NL","germany":"DE","ireland":"IE","united kingdom":"GB","uk":"GB",
    "belgium":"BE","france":"FR","australia":"AU","austria":"AT","italy":"IT",
    "portugal":"PT","czechia":"CZ","czech republic":"CZ","poland":"PL","luxembourg":"LU",
    "sweden":"SE","canada":"CA","switzerland":"CH","norway":"NO","denmark":"DK",
    "finland":"FI","spain":"ES","united states":"US","usa":"US","hong kong":"HK",
}
CODE_TO_COUNTRY_NAME = {
    "NL":"Netherlands","DE":"Germany","IE":"Ireland","GB":"United Kingdom","BE":"Belgium",
    "FR":"France","AU":"Australia","AT":"Austria","IT":"Italy","PT":"Portugal","CZ":"Czechia",
    "PL":"Poland","LU":"Luxembourg","SE":"Sweden","CA":"Canada","CH":"Switzerland",
    "NO":"Norway","DK":"Denmark","FI":"Finland","ES":"Spain","US":"United States","HK":"Hong Kong",
}

def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def make_session(retries: int = 2, backoff: float = 0.6) -> requests.Session:
    """Build the collector HTTP session with bounded retries for read/search traffic.

    Collector POST requests in this repository are idempotent discovery/search calls
    (for example Workday listing APIs and CoreHR search forms), so GET and POST share
    the same bounded retry policy. Retry-After is authoritative when a server sends it;
    otherwise urllib3's exponential backoff is used.
    """
    retry = Retry(
        total=retries, connect=retries, read=retries, status=retries,
        backoff_factor=backoff, status_forcelist=(429,500,502,503,504),
        allowed_methods=frozenset({"GET","POST"}), respect_retry_after_header=True,
    )
    session = requests.Session()
    session.headers.update({
        "User-Agent": "international-academic-job-search/0.5 (+personal research job monitor)",
        "Accept-Language": "en-GB,en;q=0.9,de;q=0.7",
    })
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session

def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script","style","noscript","svg","header","footer","nav","aside","button"]):
        tag.decompose()
    for form in soup.find_all("form"):
        form.unwrap()
    preferred_roots = [
        soup.find("main"),
        soup.find("article"),
        soup.find(attrs={"role":"main"}),
    ]
    for root in preferred_roots:
        if root is None:
            continue
        text = clean(root.get_text(" ", strip=True))
        if text:
            return text
    root = soup.body or soup
    return clean(root.get_text(" ", strip=True))

def detail_status_from_text(text: str | None, *, complete_evidence: bool) -> str:
    """Classify retrieval confidence from evidence, never from character count."""
    if not clean(text):
        return "UNAVAILABLE"
    return "FULL" if complete_evidence else "PARTIAL"

def _source_has_complete_detail_contract(source_key: str) -> bool:
    return (
        source_key in _SOURCE_SPECIFIC_COMPLETE_DETAIL_KEYS
        or source_key.startswith(_SOURCE_SPECIFIC_COMPLETE_DETAIL_PREFIXES)
    )

def normalize_detail_status(source_key: str, full_jd: str | None, status: str) -> str:
    """Make canonical Full-JD semantics authoritative at record creation.

    Collector FULL/PARTIAL values are retrieval hints. Canonical FULL requires a
    registered source-specific detail contract plus non-empty text. Unregistered
    HTML/text extraction is PARTIAL regardless of character count.
    """
    valid = {"FULL","PARTIAL","UNAVAILABLE","FETCH_FAILED","BLOCKED","NOT_ATTEMPTED"}
    normalized = status if status in valid else "FETCH_FAILED"
    if normalized not in {"FULL", "PARTIAL"}:
        return normalized
    if not clean(full_jd):
        return "UNAVAILABLE"
    return "FULL" if _source_has_complete_detail_contract(source_key) else "PARTIAL"

def fetch_detail_text(url: str, session: requests.Session | None = None, timeout=(10,45)) -> tuple[str,str]:
    s = session or make_session()
    response = s.get(url, timeout=timeout, allow_redirects=True)
    if response.status_code == 404:
        return "", "UNAVAILABLE"
    response.raise_for_status()
    content_type = (response.headers.get("content-type") or "").lower()
    if "pdf" in content_type or response.url.lower().split("?",1)[0].endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(response.content))
            text = clean(" ".join((page.extract_text() or "") for page in reader.pages))
            return text, detail_status_from_text(text, complete_evidence=True)
        except Exception:
            return "", "FETCH_FAILED"
    text = html_to_text(response.text)
    # Generic HTML extraction alone does not prove that the whole JD was isolated.
    return text, detail_status_from_text(text, complete_evidence=False)

def infer_country_code(country_name: str | None = None, location_text: str | None = None) -> str | None:
    candidates = [clean(country_name).lower(), clean(location_text).lower()]
    for text in candidates:
        if not text:
            continue
        if len(text) == 2 and text.upper() in CODE_TO_COUNTRY_NAME:
            return text.upper()
        for name, code in sorted(COUNTRY_NAME_TO_CODE.items(), key=lambda kv: -len(kv[0])):
            if re.search(rf"\b{re.escape(name)}\b", text, re.I):
                return code
    return None

def market_tier(country_code: str | None) -> str:
    if country_code in CORE_COUNTRIES:
        return "CORE"
    if country_code in OPPORTUNISTIC_COUNTRIES:
        return "OPPORTUNISTIC"
    if country_code in EXCLUDED_COUNTRIES:
        return "EXCLUDED"
    return "UNKNOWN"

def fingerprint(payload: Any) -> str:
    return hashlib.sha256(repr(payload).encode("utf-8","replace")).hexdigest()

def day_iso(value: str | None, *, reference: datetime | None = None) -> str | None:
    """Normalize source dates to midnight UTC without guessing ambiguous US dates.

    Supports ISO timestamps, common European/academic-board date formats, ordinal
    suffixes, benign labels such as ``Posted``/``Closing date``, and Workday-style
    relative posting dates. Slash-separated numeric dates are interpreted day-first,
    matching the repository's European/UK source scope.
    """
    text = clean(value)
    if not text:
        return None

    # Remove source labels without consuming meaningful date words.
    text = re.sub(
        r"^(?:posted(?:\s+on)?|published(?:\s+on)?|closing\s+date|applications?\s+close|deadline)\s*:?\s*",
        "", text, flags=re.I,
    ).strip()
    text = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", text, flags=re.I)

    base = reference or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    else:
        base = base.astimezone(timezone.utc)

    low = text.lower().strip(" .")
    if low in {"today", "posted today"}:
        dt = base
        return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if low in {"yesterday", "posted yesterday"}:
        dt = base - timedelta(days=1)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    relative = re.fullmatch(r"(?:posted\s+)?(\d+)\+?\s+days?\s+ago", low)
    if relative:
        dt = base - timedelta(days=int(relative.group(1)))
        return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Preserve the source's calendar date. These schema fields model a day, not an
    # instant, so converting an ISO offset to UTC must not move it to another day.
    iso_day = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[Tt\s].*)?$", text)
    if iso_day:
        try:
            dt = datetime.strptime(iso_day.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass

    formats = (
        "%Y-%m-%d", "%Y/%m/%d",
        "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d %m %Y",
        "%d %B %Y", "%d %b %Y",
        "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass
    return None

def make_record(
    *, source_key: str, source_kind: str, provider: str, source_job_id: str,
    listing_url: str, detail_url: str | None, title: str,
    institution: str | None = None, department: str | None = None,
    country_name: str | None = None, country_code: str | None = None,
    city: str | None = None, region: str | None = None,
    posted_text: str | None = None, deadline_text: str | None = None,
    full_jd: str | None = None, detail_status: str = "NOT_ATTEMPTED",
    detail_failure_reason: str | None = None, apply_url: str | None = None,
    source_language: str | None = None, source_status: str = "UNKNOWN",
    raw_extra: dict[str,Any] | None = None,
) -> dict[str,Any]:
    now=utc_now_iso()
    date_reference=datetime.fromisoformat(now)
    if source_kind == "CORE_MARKET_PORTAL":
        source_kind = "DIRECT_INSTITUTION" if source_key == "uibk" else "NATIONAL_PORTAL"
    code = country_code or infer_country_code(country_name, " ".join(filter(None,[city,region,country_name])))
    cname = country_name or (CODE_TO_COUNTRY_NAME.get(code) if code else None)
    detail_status = normalize_detail_status(source_key, full_jd, detail_status)
    review_codes=["COLLECTOR_ONLY_NOT_PRE_EVALUATED"]
    disposition="POLICY_REVIEW"
    if detail_status not in {"FULL","PARTIAL"}:
        disposition="NEEDS_DETAIL_REVIEW"
        review_codes.append("FULL_JD_UNAVAILABLE")
    return {
        "schema_version": SCHEMA_VERSION,
        "record_stage": "SHARD_ENRICHED",
        "source_record_id": f"{source_key}:{source_job_id}",
        "canonical_id": None,
        "source": {
            "source_key": source_key, "source_kind": source_kind, "provider": provider,
            "source_job_id": str(source_job_id), "listing_url": listing_url,
            "detail_url": detail_url, "apply_url": apply_url, "retrieved_at": now,
            "source_language": source_language, "source_status": source_status,
        },
        "position": {
            "title_raw": clean(title), "title_normalized": None,
            "institution_raw": clean(institution) or None, "institution_normalized": None,
            "department": clean(department) or None, "role_family": "UNKNOWN",
            "role_level": "UNKNOWN", "employment_type": "UNKNOWN", "workplace_mode": "UNKNOWN",
        },
        "location": {"country_code": code, "country_name": cname, "city": clean(city) or None, "region": clean(region) or None},
        "dates": {
            "posted_at": day_iso(posted_text, reference=date_reference),
            "deadline_at": day_iso(deadline_text, reference=date_reference),
            "deadline_text": clean(deadline_text) or None,
            "deadline_status": "KNOWN" if clean(deadline_text) else "UNKNOWN",
            "collected_at": now,
        },
        "contract": {
            "term_type": "UNKNOWN", "duration_months": None, "fte": None,
            "salary": {"min":None,"max":None,"currency":None,"period":"UNKNOWN","raw_text":None},
        },
        "description": {
            "full_jd": clean(full_jd) or None, "detail_status": detail_status,
            "detail_failure_reason": clean(detail_failure_reason) or None,
            "detail_retrieved_at": now if detail_status in {"FULL","PARTIAL"} else None,
        },
        "requirements": {
            "phd_requirement":"UNKNOWN","degree_text":None,"degree_fields":[],"years_postdoc":None,
            "language_requirements":[],"work_rights_text":None,"sponsorship_text":None,
            "professional_registration_text":None,"teaching_requirement_text":None,
            "methods_required":[],"methods_preferred":[],
        },
        "classification": {
            "market_tier": market_tier(code), "role_policy_status":"AMBIGUOUS",
            "pre_evaluation_disposition": disposition, "review_codes":review_codes,"blocker_codes":[],
        },
        "provenance": {
            "observed_by_sources":[source_key],
            "raw_payload_fingerprint": fingerprint(raw_extra or {"title":title,"url":detail_url or listing_url}),
            "notes":["Collector output; no scientific-fit decision made."],
        },
        "raw_extra": raw_extra or {},
    }
