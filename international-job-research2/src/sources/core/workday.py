from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from src.sources.shared.pagination import paginate, reached, record_coverage
from src.sources.shared.common import clean, make_record, make_session


@dataclass(frozen=True)
class WorkdayTenant:
    key: str
    provider: str
    host: str
    tenant: str
    site: str
    country_code: str = "AU"
    country_name: str = "Australia"

    @property
    def public_base(self) -> str:
        return f"https://{self.host}/en-US/{self.site}"

    @property
    def cxs_base(self) -> str:
        return f"https://{self.host}/wday/cxs/{self.tenant}/{self.site}"


TENANTS: dict[str, WorkdayTenant] = {
    "uq": WorkdayTenant("uq", "The University of Queensland", "uq.wd3.myworkdayjobs.com", "uq", "uqcareers"),
    "flinders": WorkdayTenant("flinders", "Flinders University", "flinders.wd3.myworkdayjobs.com", "flinders", "flinders_employment"),
    "usyd": WorkdayTenant("usyd", "The University of Sydney", "usyd.wd105.myworkdayjobs.com", "usyd", "USYD_EXTERNAL_CAREER_SITE"),
}


def _strip_html(value: Any) -> str:
    if value is None:
        return ""
    soup = BeautifulSoup(html_lib.unescape(str(value)), "html.parser")
    return clean(soup.get_text(" ", strip=True))


def _job_id(external_path: str, fallback: str = "") -> str:
    path = clean(external_path)
    tail = path.rstrip("/").split("/")[-1]
    m = re.search(r"_((?:R|JR|REQ|REQID)[-_]?[A-Za-z0-9.-]+)$", tail, re.I)
    if m:
        return m.group(1)
    m = re.search(r"([A-Za-z]*\d{5,}(?:-\d+)?)$", tail)
    if m:
        return m.group(1)
    return clean(fallback) or re.sub(r"[^a-z0-9]+", "-", tail.lower()).strip("-")[-120:] or "unknown"


def parse_search_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("jobPostings") or payload.get("items") or []
    out: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = clean(row.get("title"))
        path = clean(row.get("externalPath") or row.get("path"))
        if not title or not path:
            continue
        if not path.startswith("/"):
            path = "/" + path
        bullets = row.get("bulletFields") or []
        if not isinstance(bullets, list):
            bullets = []
        out.append({
            "id": _job_id(path, clean(row.get("jobReqId"))),
            "title": title,
            "external_path": path,
            "location": clean(row.get("locationsText") or row.get("location")) or None,
            "posted": clean(row.get("postedOn") or row.get("posted")) or None,
            "bullet_fields": [clean(x) for x in bullets if clean(x)],
            "raw": row,
        })
    return out


def parse_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    info = payload.get("jobPostingInfo") or payload.get("jobPosting") or payload
    if not isinstance(info, dict):
        info = {}
    description = _strip_html(info.get("jobDescription") or info.get("description"))
    return {
        "title": clean(info.get("title")) or None,
        "description": description,
        "location": clean(info.get("location") or info.get("locationText")) or None,
        "posted": clean(info.get("postedOn") or info.get("postedDate")) or None,
        "start_date": clean(info.get("startDate")) or None,
        "time_type": clean(info.get("timeType")) or None,
        "worker_subtype": clean(info.get("workerSubType")) or None,
        "job_req_id": clean(info.get("jobReqId") or info.get("requisitionId")) or None,
        "external_url": clean(info.get("externalUrl")) or None,
        "apply_url": clean(info.get("applyUrl")) or None,
    }


def _listing_payload(session, tenant: WorkdayTenant, *, offset: int, limit: int) -> dict[str, Any]:
    response = session.post(
        f"{tenant.cxs_base}/jobs",
        json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=(10, 45),
    )
    response.raise_for_status()
    payload = response.json()
    if "jobPostings" not in payload and "items" not in payload:
        raise ValueError("Workday listing payload has no job collection")
    return payload


def _discover_usyd(tenant: WorkdayTenant, *, max_jobs: int | None, session) -> list[dict[str, Any]]:
    """USyd Workday repeats page zero beyond its raw advertised result window.

    Completion therefore follows raw API positions, while only parseable public jobs are
    emitted. Public/parser job IDs are unchanged; external_path is used only for internal
    deduplication so a malformed raw item cannot force an extra repeated request.
    """
    page_size = min(max_jobs, 20) if max_jobs is not None else 20
    rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    raw_records = 0
    skipped_unparseable = 0
    advertised_total: int | None = None
    pages = 0
    offset = 0
    reason = "unknown"
    complete = False
    error = None

    while True:
        try:
            payload = _listing_payload(session, tenant, offset=offset, limit=page_size)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            reason = "request_failed"
            if pages == 0:
                record_coverage(
                    f"workday_{tenant.key}", reason, complete=False, pages=0, records=0,
                    advertised_total=advertised_total, raw_records=0, skipped_unparseable=0,
                    error=error,
                )
                raise
            break

        pages += 1
        raw = payload.get("jobPostings") or payload.get("items") or []
        if not isinstance(raw, list):
            raw = []
        raw_count = len(raw)
        raw_records += raw_count
        parsed = parse_search_payload(payload)
        skipped_unparseable += max(0, raw_count - len(parsed))

        value = payload.get("total")
        try:
            positive_total = int(value) if value is not None and int(value) > 0 else None
        except (TypeError, ValueError):
            positive_total = None
        if positive_total is not None:
            advertised_total = max(advertised_total or 0, positive_total)

        for item in parsed:
            key = item["external_path"]
            if key in seen_paths:
                continue
            seen_paths.add(key)
            rows.append(item)
            if reached(rows, max_jobs):
                break

        if reached(rows, max_jobs):
            reason = "configured_record_limit"
            break
        if raw_count == 0:
            reason = "empty_page"
            complete = advertised_total is None or offset >= advertised_total
            break
        if advertised_total is not None and offset + raw_count >= advertised_total:
            reason = "advertised_total_window_reached"
            complete = True
            break
        if advertised_total is None and raw_count < page_size:
            reason = "last_page"
            complete = True
            break
        offset += page_size

    record_coverage(
        f"workday_{tenant.key}", reason, complete=complete, pages=pages, records=len(rows),
        advertised_total=advertised_total, raw_records=raw_records,
        skipped_unparseable=skipped_unparseable, error=error,
    )
    return rows


def discover(tenant: WorkdayTenant, *, max_jobs: int | None = 100, session=None) -> list[dict[str, Any]]:
    s = session or make_session()
    if tenant.key == "usyd":
        return _discover_usyd(tenant, max_jobs=max_jobs, session=s)

    # Workday rejects oversized pages on some tenants; page size is not a total cap.
    page_size = min(max_jobs, 20) if max_jobs is not None else 20
    def fetch(page):
        payload = _listing_payload(s, tenant, offset=page * page_size, limit=page_size)
        return parse_search_payload(payload), payload.get("total"), None
    return paginate(fetch, source=f"workday_{tenant.key}", max_jobs=max_jobs)



def collect(*, tenant_key: str, max_jobs: int | None = 100, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    if tenant_key not in TENANTS:
        raise KeyError(f"Unknown Workday tenant: {tenant_key}")
    tenant = TENANTS[tenant_key]
    s = session or make_session()
    candidates = discover(tenant, max_jobs=max_jobs, session=s)
    out: list[dict[str, Any]] = []
    for item in candidates:
        external_path = item["external_path"]
        public_url = f"https://{tenant.host}/en-US/{tenant.site}{external_path}"
        cxs_detail = f"{tenant.cxs_base}{external_path}"
        parsed: dict[str, Any] = {}
        detail = None
        status = "NOT_ATTEMPTED"
        failure = None
        if enrich_detail:
            try:
                response = s.get(cxs_detail, headers={"Accept": "application/json"}, timeout=(10, 45))
                response.raise_for_status()
                parsed = parse_detail_payload(response.json())
                detail = parsed.get("description") or ""
                status = "FULL" if len(detail) >= 200 else ("PARTIAL" if detail else "UNAVAILABLE")
            except Exception as exc:
                status = "FETCH_FAILED"
                failure = f"{type(exc).__name__}: {exc}"
        out.append(
            make_record(
                source_key=f"workday_{tenant.key}",
                source_kind="ATS",
                provider=tenant.provider,
                source_job_id=parsed.get("job_req_id") or item["id"],
                listing_url=tenant.public_base,
                detail_url=parsed.get("external_url") or public_url,
                apply_url=parsed.get("apply_url"),
                title=parsed.get("title") or item["title"],
                institution=tenant.provider,
                country_code=tenant.country_code,
                country_name=tenant.country_name,
                city=parsed.get("location") or item.get("location"),
                posted_text=parsed.get("posted") or item.get("posted"),
                full_jd=detail,
                detail_status=status,
                detail_failure_reason=failure,
                source_language="en",
                source_status="UNKNOWN",
                raw_extra={
                    "tenant": tenant.key,
                    "external_path": external_path,
                    "cxs_detail_url": cxs_detail,
                    "time_type": parsed.get("time_type"),
                    "worker_subtype": parsed.get("worker_subtype"),
                    "start_date": parsed.get("start_date"),
                    "bullet_fields": item.get("bullet_fields", []),
                },
            )
        )
    return out
