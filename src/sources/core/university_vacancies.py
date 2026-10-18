from __future__ import annotations

from typing import Any

from src.sources.shared.pagination import paginate
from src.sources.shared.common import clean, html_to_text, make_record, make_session

BASE_URL = "https://universityvacancies.com"
LISTING_URL = f"{BASE_URL}/search"
PUBLIC_API_URL = f"{BASE_URL}/api/job-posts/public"


def _iso_day(value: Any) -> str | None:
    text = clean(value)
    return text[:10] if len(text) >= 10 else (text or None)


def _normalized_source_status(value: Any) -> str:
    status = clean(value).lower()
    if status in {"published", "open", "active"}:
        return "OPEN"
    if status in {"closed", "expired", "inactive", "unpublished"}:
        return "CLOSED"
    if status == "error":
        return "ERROR"
    return "UNKNOWN"


def _payload_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    rows = data.get("jobPosts")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def parse_search_payload(payload: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in _payload_rows(payload):
        source_id = row.get("id")
        title = clean(row.get("title"))
        if source_id is None or not title:
            continue

        institution = row.get("institution") if isinstance(row.get("institution"), dict) else {}
        category = row.get("category") if isinstance(row.get("category"), dict) else {}
        job_type = row.get("jobType") if isinstance(row.get("jobType"), dict) else {}
        description = html_to_text(str(row.get("description") or ""))

        out.append({
            "id": str(source_id),
            "reference": clean(row.get("reference") or row.get("coreHrId")) or None,
            "title": title,
            "slug": clean(row.get("slug")) or None,
            "institution": clean(institution.get("institutionName")) or None,
            "institution_slug": clean(institution.get("slug")) or None,
            "location": clean(row.get("location")) or None,
            "posted": _iso_day(row.get("publishedAt") or row.get("publishFrom")),
            "deadline": _iso_day(row.get("closingDate") or row.get("publishTo")),
            "description": description,
            "apply_url": clean(row.get("applyUrl")) or None,
            "source_status": _normalized_source_status(row.get("status")),
            "source_status_raw": clean(row.get("status")) or None,
            "source_system": clean(row.get("source")) or None,
            "category": clean(category.get("name")) or None,
            "job_type": clean(job_type.get("displayName") or job_type.get("name")) or None,
            "raw": row,
        })
    return out


def _detail_from_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def collect(*, max_jobs: int | None = 80, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    s = session or make_session()
    limit = min(max_jobs, 100) if max_jobs is not None else 100
    def fetch(page):
        response = s.get(PUBLIC_API_URL, params={"page": page, "limit": limit},
                         timeout=(10, 45), allow_redirects=True)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload.get("data"), dict) or "jobPosts" not in payload["data"]:
            raise ValueError("University Vacancies listing payload has no jobPosts")
        return parse_search_payload(payload), (payload["data"].get("pagination") or {}).get("total"), None
    candidates = paginate(fetch, source="university_vacancies_ie", max_jobs=max_jobs, start=1)

    out: list[dict[str, Any]] = []
    for item in candidates:
        detail_text = clean(item.get("description"))
        detail_status = "FULL" if len(detail_text) >= 200 else ("PARTIAL" if detail_text else "UNAVAILABLE")
        failure = None

        if enrich_detail and detail_status == "UNAVAILABLE":
            try:
                detail_response = s.get(
                    f"{PUBLIC_API_URL}/{item['id']}",
                    timeout=(10, 45),
                    allow_redirects=True,
                )
                if detail_response.status_code == 404:
                    detail_status = "UNAVAILABLE"
                else:
                    detail_response.raise_for_status()
                    detail_row = _detail_from_payload(detail_response.json())
                    if detail_row:
                        detail_text = html_to_text(str(detail_row.get("description") or ""))
                        detail_status = "FULL" if len(detail_text) >= 200 else ("PARTIAL" if detail_text else "UNAVAILABLE")
            except Exception as exc:
                detail_status = "FETCH_FAILED"
                failure = f"{type(exc).__name__}: {exc}"

        detail_url = f"{PUBLIC_API_URL}/{item['id']}"
        out.append(
            make_record(
                source_key="university_vacancies_ie",
                source_kind="NATIONAL_PORTAL",
                provider="University Vacancies Ireland",
                source_job_id=item["id"],
                listing_url=LISTING_URL,
                detail_url=detail_url,
                title=item["title"],
                institution=item.get("institution"),
                country_code="IE",
                country_name="Ireland",
                city=item.get("location"),
                posted_text=item.get("posted"),
                deadline_text=item.get("deadline"),
                full_jd=detail_text,
                detail_status=detail_status,
                detail_failure_reason=failure,
                apply_url=item.get("apply_url"),
                source_language="en",
                source_status=item.get("source_status") or "UNKNOWN",
                raw_extra={
                    "reference": item.get("reference"),
                    "institution_slug": item.get("institution_slug"),
                    "job_slug": item.get("slug"),
                    "upstream_source": item.get("source_system"),
                    "source_status_raw": item.get("source_status_raw"),
                    "category": item.get("category"),
                    "job_type": item.get("job_type"),
                },
            )
        )
    return out
