from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from src.sources.shared.pagination import html_pages
from src.sources.shared.common import clean, html_to_text, make_record, make_session


@dataclass(frozen=True)
class CoreHRTenant:
    key: str
    provider: str
    search_url: str
    country_code: str = "IE"
    country_name: str = "Ireland"
    language: str = "en"


TENANTS: dict[str, CoreHRTenant] = {
    "ucd": CoreHRTenant("ucd", "University College Dublin", "https://my.corehr.com/pls/ucdrecruit/erq_search_package.search_form?p_company=1&p_internal_external=E"),
    "dcu": CoreHRTenant("dcu", "Dublin City University", "https://my.corehr.com/pls/dcurecruit/erq_search_package.search_form?p_company=1&p_internal_external=E"),
    "ucc": CoreHRTenant("ucc", "University College Cork", "https://my.corehr.com/pls/uccrecruit/erq_search_package.search_form?p_company=5023&p_internal_external=E"),
    "tcd": CoreHRTenant("tcd", "Trinity College Dublin", "https://my.corehr.com/pls/trrecruit/erq_search_package.search_form?p_company=1&p_internal_external=E"),
    "galway": CoreHRTenant("galway", "University of Galway", "https://my.corehr.com/pls/nuigrecruit/erq_search_package.search_form?p_company=1&p_internal_external=E"),
}


def _search_form(soup: BeautifulSoup):
    forms = soup.find_all("form")
    for form in forms:
        name = clean(form.get("name")).lower()
        action = clean(form.get("action")).lower()
        if name == "callerecruitdosearch" or "start_search_with_params" in action:
            return form
    for form in forms:
        names = {clean(tag.get("name")).lower() for tag in form.find_all(["input", "select", "button"]) if tag.get("name")}
        if {"p_company", "p_internal_external", "p_competition_type"}.issubset(names) and ("p_keywords" in names or "p_recruitment_id" in names):
            return form
    return None


def _form_payload_and_action(html: str, page_url: str) -> tuple[str, list[tuple[str, str]]]:
    soup = BeautifulSoup(html or "", "html.parser")
    form = _search_form(soup)
    if form is None:
        return page_url, []
    action = urljoin(page_url, str(form.get("action") or page_url))
    data: list[tuple[str, str]] = []
    for inp in form.find_all(["input", "select"]):
        name = inp.get("name")
        if not name:
            continue
        if inp.name == "select":
            option = inp.find("option", selected=True) or inp.find("option")
            if option and option.get("value") is not None:
                data.append((str(name), str(option.get("value") or "")))
            continue
        typ = str(inp.get("type") or "text").lower()
        if typ in {"submit", "button", "image", "file"}:
            continue
        if typ in {"checkbox", "radio"} and not inp.has_attr("checked"):
            continue
        data.append((str(name), str(inp.get("value") or "")))
    submit = form.find(["input", "button"], attrs={"type": re.compile(r"submit", re.I)})
    if submit and submit.get("name"):
        data.append((str(submit.get("name")), str(submit.get("value") or submit.get_text(" ", strip=True) or "Search")))
    return action, data


def _company_from_page(soup: BeautifulSoup, base_url: str) -> str:
    company = soup.find("input", attrs={"name": "p_company"})
    if company and company.get("value"):
        return clean(company.get("value"))
    query = parse_qs(urlparse(base_url).query)
    return clean((query.get("p_company") or [""])[0])


def _detail_url(base_url: str, recruitment_id: str, company: str) -> str:
    endpoint = urljoin(base_url, "erq_jobspec_version_4.display_form")
    params = {
        "p_applicant_no": "",
        "p_company": company,
        "p_display_apply_ind": "Y",
        "p_display_in_irish": "N",
        "p_form_profile_detail": "",
        "p_internal_external": "E",
        "p_process_type": "",
        "p_recruitment_id": recruitment_id,
        "p_refresh_search": "Y",
    }
    return f"{endpoint}?{urlencode(params)}"


def _better_listing_title(block, current_title: str) -> str:
    if not block:
        return current_title
    cells = [clean(td.get_text(" ", strip=True)) for td in block.find_all(["td", "th"])]
    current = clean(current_title)
    for candidate in cells:
        if not candidate or len(candidate) <= len(current):
            continue
        if re.search(r"close|date|reference|job id|job spec|more|apply", candidate, re.I):
            continue
        if current and candidate.lower().startswith(current.lower()):
            return candidate
    if current.lower() in {"job spec more ->", "job spec more", "details", "view", "more"} or len(current) < 5:
        return next((c for c in cells if len(c) > 5 and not re.search(r"close|date|reference|job id|job spec|more|apply", c, re.I)), current)
    return current


def parse_listing(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    company = _company_from_page(soup, base_url)

    for a in soup.find_all("a", href=True):
        raw_href = str(a.get("href") or "").strip()
        href = urljoin(base_url, raw_href)
        rid = ""

        if "erq_jobspec_version_4.display_form" in href:
            qs = parse_qs(urlparse(href).query)
            rid = clean((qs.get("p_recruitment_id") or [""])[0])
        else:
            js_match = re.search(r"viewTheJobSpec\(\s*['\"]([^'\"]+)['\"]\s*\)", raw_href, re.I)
            if js_match:
                rid = clean(js_match.group(1))
                href = _detail_url(base_url, rid, company)

        if not rid or rid in seen:
            continue

        block = a.find_parent("tr") or a.find_parent(["li", "div", "p"]) or a.parent
        context = clean(block.get_text(" | ", strip=True)) if block else clean(a.get_text(" ", strip=True))
        title = _better_listing_title(block, clean(a.get_text(" ", strip=True)))
        close_m = re.search(r"(?:Close|Closing)\s*Date\s*:?\s*([^|]+)", context, re.I)
        seen.add(rid)
        out.append({
            "id": rid,
            "title": title or f"CoreHR vacancy {rid}",
            "url": href,
            "deadline": clean(close_m.group(1)) if close_m else "",
            "context": context,
        })
    return out


def _detail_heading_title(soup: BeautifulSoup, fallback_title: str) -> str:
    fallback = clean(fallback_title)
    generic = {"vacancy details", "job details", "job specification", "career opportunities", "e-recruitment", "erecruitment"}
    for node in soup.find_all(["h1", "h2", "h3", "h4"]):
        candidate = clean(node.get_text(" ", strip=True))
        if not candidate or candidate.lower() in generic:
            continue
        if len(candidate) > len(fallback) and (not fallback or candidate.lower().startswith(fallback.lower())):
            return candidate
    return fallback


def _detail_banner_title(text: str, fallback_title: str) -> str:
    fallback = clean(fallback_title)
    normalized = clean(text)
    stop_pattern = re.compile(
        r",\s*(?:Full[- ]Time|Part[- ]Time|Permanent|Temporary|Fixed[- ]Term|Specified Purpose|Contract)\b|"
        r"\s+Applications are invited\b|\s+(?:Close|Closing)\s+Date\b|\s+Job\s+ID\b",
        re.I,
    )
    for marker in re.finditer(r"\bVacancies\s+", normalized, re.I):
        tail = normalized[marker.end(): marker.end() + 500]
        candidate = clean(stop_pattern.split(tail, maxsplit=1)[0])
        if not candidate:
            continue
        if fallback and not candidate.lower().startswith(fallback.lower()):
            continue
        if len(candidate) > len(fallback):
            return candidate
    return fallback


def parse_detail(html: str, fallback_title: str = "") -> dict[str, str]:
    soup = BeautifulSoup(html or "", "html.parser")
    text = html_to_text(html)
    title = _detail_heading_title(soup, fallback_title)
    title = _detail_banner_title(text, title)
    title_m = re.search(
        r"Job Title\s*:\s*(.+?)(?=\s*(?:\|\s*)?(?:Pay Scale|Close Date|Closing Date|Contact|Job ID|$))",
        text,
        re.I,
    )
    if title_m and clean(title_m.group(1)):
        title = clean(title_m.group(1))
    elif not title:
        fallback_m = re.search(r"^\s*Vacancy Details\s+(.+?)(?=\s*(?:\||$))", text, re.I | re.M)
        if fallback_m:
            title = clean(fallback_m.group(1))
    close_m = re.search(
        r"(?:Close|Closing)\s*Date\s*:\s*(.+?)(?=\s*(?:\|\s*)?(?:Contact|Job ID|Pay Scale|$))",
        text,
        re.I,
    )
    return {"title": title, "deadline": clean(close_m.group(1)) if close_m else "", "description": text}


def discover(tenant: CoreHRTenant, *, session=None) -> list[dict[str, Any]]:
    s = session or make_session()
    initial = s.get(tenant.search_url, timeout=(10, 45), allow_redirects=True)
    initial.raise_for_status()
    direct = parse_listing(initial.text, initial.url)
    if direct:
        return html_pages(s, initial.url, parse_listing, initial_response=initial)
    action, payload = _form_payload_and_action(initial.text, initial.url)
    if not payload or action == initial.url:
        return []
    response = s.post(action, data=payload, timeout=(10, 45), allow_redirects=True)
    response.raise_for_status()
    return html_pages(s, response.url, parse_listing, initial_response=response)


def collect(*, tenant_key: str, max_jobs: int | None = 80, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    if tenant_key not in TENANTS:
        raise KeyError(f"Unknown CoreHR tenant: {tenant_key}")
    tenant = TENANTS[tenant_key]
    s = session or make_session()
    candidates = discover(tenant, session=s)[:max_jobs]
    out: list[dict[str, Any]] = []
    for item in candidates:
        detail = None
        status = "NOT_ATTEMPTED"
        failure = None
        parsed: dict[str, str] = {}
        if enrich_detail:
            try:
                response = s.get(item["url"], timeout=(10, 45), allow_redirects=True)
                response.raise_for_status()
                parsed = parse_detail(response.text, item["title"])
                detail = parsed.get("description") or ""
                status = "FULL" if len(detail) >= 200 else ("PARTIAL" if detail else "UNAVAILABLE")
            except Exception as exc:
                status = "FETCH_FAILED"
                failure = f"{type(exc).__name__}: {exc}"
        out.append(
            make_record(
                source_key=f"corehr_{tenant.key}",
                source_kind="ATS",
                provider=tenant.provider,
                source_job_id=item["id"],
                listing_url=tenant.search_url,
                detail_url=item["url"],
                title=parsed.get("title") or item["title"],
                institution=tenant.provider,
                country_code=tenant.country_code,
                country_name=tenant.country_name,
                deadline_text=parsed.get("deadline") or item.get("deadline") or None,
                full_jd=detail,
                detail_status=status,
                detail_failure_reason=failure,
                source_language=tenant.language,
                source_status="UNKNOWN",
                raw_extra={"tenant": tenant.key, "listing_context": item.get("context", "")},
            )
        )
    return out
