from __future__ import annotations

import html as html_lib
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from src.sources.shared.pagination import paginate
from src.sources.shared.common import clean, make_record, make_session


API_BASE = "https://api.smartrecruiters.com/v1/companies"


@dataclass(frozen=True)
class SmartRecruitersTenant:
    key: str
    provider: str
    company_identifier: str
    country_code: str = "AU"
    country_name: str = "Australia"


TENANTS: dict[str, SmartRecruitersTenant] = {
    "western_sydney": SmartRecruitersTenant("western_sydney", "Western Sydney University", "WesternSydneyUniversity"),
    "griffith": SmartRecruitersTenant("griffith", "Griffith University", "GriffithUniversity"),
}


def _strip_html(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    soup = BeautifulSoup(html_lib.unescape(value), "html.parser")
    return clean(soup.get_text(" ", strip=True))


def parse_search_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("content") or payload.get("results") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        job_id = clean(row.get("id"))
        title = clean(row.get("name") or row.get("title"))
        if not job_id or not title:
            continue
        location = row.get("location") or {}
        if not isinstance(location, dict):
            location = {}
        company = row.get("company") or {}
        if not isinstance(company, dict):
            company = {}
        out.append({
            "id": job_id,
            "title": title,
            "institution": clean(company.get("name")) or None,
            "city": clean(location.get("city")) or None,
            "country": clean(location.get("country")) or None,
            "posted": clean(row.get("releasedDate") or row.get("createdOn")) or None,
            "ref": clean(row.get("refNumber")) or None,
            "raw": row,
        })
    return out


def parse_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sections = ((payload.get("jobAd") or {}).get("sections") or {}) if isinstance(payload.get("jobAd") or {}, dict) else {}
    parts: list[str] = []
    if isinstance(sections, dict):
        for key in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"):
            section = sections.get(key)
            if isinstance(section, dict):
                text = _strip_html(section.get("text") or section.get("title"))
            else:
                text = _strip_html(section)
            if text:
                parts.append(text)
    location = payload.get("location") or {}
    if not isinstance(location, dict):
        location = {}
    company = payload.get("company") or {}
    if not isinstance(company, dict):
        company = {}
    return {
        "title": clean(payload.get("name") or payload.get("title")),
        "institution": clean(company.get("name")) or None,
        "city": clean(location.get("city")) or None,
        "country": clean(location.get("country")) or None,
        "description": clean(" ".join(parts)),
        "apply_url": clean(((payload.get("apply") or {}).get("url") if isinstance(payload.get("apply") or {}, dict) else None)) or None,
        "ref": clean(payload.get("refNumber")) or None,
    }


def collect(*, tenant_key: str, max_jobs: int | None = 100, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    if tenant_key not in TENANTS:
        raise KeyError(f"Unknown SmartRecruiters tenant: {tenant_key}")
    tenant = TENANTS[tenant_key]
    s = session or make_session()
    search_url = f"{API_BASE}/{tenant.company_identifier}/postings"
    page_size = min(max_jobs, 100) if max_jobs is not None else 100
    def fetch(page):
        response = s.get(search_url, params={"limit": page_size, "offset": page * page_size}, timeout=(10, 45))
        response.raise_for_status()
        payload = response.json()
        if "content" not in payload and "results" not in payload:
            raise ValueError("SmartRecruiters listing payload has no job collection")
        return parse_search_payload(payload), payload.get("totalFound"), None
    candidates = paginate(fetch, source=f"smartrecruiters_{tenant.key}", max_jobs=max_jobs)
    out: list[dict[str, Any]] = []
    for item in candidates:
        detail_url = f"{API_BASE}/{tenant.company_identifier}/postings/{item['id']}"
        detail = None
        status = "NOT_ATTEMPTED"
        failure = None
        parsed: dict[str, Any] = {}
        if enrich_detail:
            try:
                r = s.get(detail_url, timeout=(10, 45))
                r.raise_for_status()
                parsed = parse_detail_payload(r.json())
                detail = parsed.get("description") or ""
                status = "FULL" if len(detail) >= 200 else ("PARTIAL" if detail else "UNAVAILABLE")
            except Exception as exc:
                status = "FETCH_FAILED"
                failure = f"{type(exc).__name__}: {exc}"
        out.append(
            make_record(
                source_key=f"smartrecruiters_{tenant.key}",
                source_kind="ATS",
                provider=tenant.provider,
                source_job_id=item["id"],
                listing_url=f"https://jobs.smartrecruiters.com/{tenant.company_identifier}",
                detail_url=f"https://jobs.smartrecruiters.com/{tenant.company_identifier}/{item['id']}",
                apply_url=parsed.get("apply_url"),
                title=parsed.get("title") or item["title"],
                institution=parsed.get("institution") or item.get("institution") or tenant.provider,
                country_code=tenant.country_code,
                country_name=tenant.country_name,
                city=parsed.get("city") or item.get("city"),
                posted_text=item.get("posted"),
                full_jd=detail,
                detail_status=status,
                detail_failure_reason=failure,
                source_language="en",
                source_status="UNKNOWN",
                raw_extra={"tenant": tenant.key, "ref_number": parsed.get("ref") or item.get("ref"), "api_detail_url": detail_url},
            )
        )
    return out
