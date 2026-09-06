from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.sources.shared.pagination import html_pages
from src.sources.shared.common import clean, fetch_detail_text, make_record, make_session


ACADEMICTRANSFER_URL = "https://www.academictransfer.com/en/jobs/?order=published"
ACADEMICS_URL = "https://www.academics.de/stellenanzeigen"
UNIVERSITY_VACANCIES_URL = "https://universityvacancies.com/search"
CNRS_URL = "https://emploi.cnrs.fr/Offres/Recherche.aspx"
UNIROLES_URL = "https://uniroles.com.au/academic-uni-jobs/"
INNSBRUCK_URL = "https://lfuonline.uibk.ac.at/public/karriereportal.home?lang=en"


def _block_text(anchor) -> str:
    block = anchor.find_parent(["article", "li", "tr", "div"]) or anchor.parent
    return clean(block.get_text(" | ", strip=True)) if block else clean(anchor.get_text(" ", strip=True))


def _stable_tail_id(url: str) -> str:
    path = urlparse(url).path.strip("/")
    m = re.search(r"(?:^|/)(\d{4,})(?:/|$)", path)
    if m:
        return m.group(1)
    m = re.search(r"(\d{4,})$", path)
    if m:
        return m.group(1)
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return slug[-120:] or "unknown"


def _generic_collect(
    *,
    source_key: str,
    provider: str,
    listing_url: str,
    parser: Callable[[str, str], list[dict[str, Any]]],
    country_code: str | None,
    country_name: str | None,
    source_language: str,
    max_jobs: int | None,
    enrich_detail: bool,
    session=None,
) -> list[dict[str, Any]]:
    s = session or make_session()
    candidates = html_pages(s, listing_url, parser, max_jobs=max_jobs)
    out: list[dict[str, Any]] = []
    for item in candidates:
        detail = None
        detail_status = "NOT_ATTEMPTED"
        failure = None
        if enrich_detail:
            try:
                detail, detail_status = fetch_detail_text(item["url"], s)
            except Exception as exc:
                detail_status = "FETCH_FAILED"
                failure = f"{type(exc).__name__}: {exc}"
        code = item.get("country_code") or country_code
        cname = item.get("country_name") or country_name
        out.append(
            make_record(
                source_key=source_key,
                source_kind="CORE_MARKET_PORTAL",
                provider=provider,
                source_job_id=str(item["id"]),
                listing_url=listing_url,
                detail_url=item["url"],
                title=item.get("title") or "",
                institution=item.get("institution"),
                country_code=code,
                country_name=cname,
                city=item.get("city"),
                deadline_text=item.get("deadline"),
                posted_text=item.get("posted"),
                full_jd=detail,
                detail_status=detail_status,
                detail_failure_reason=failure,
                source_language=source_language,
                source_status="UNKNOWN",
                raw_extra={"listing_context": item.get("context", "")},
            )
        )
    return out


# ------------------------------- Netherlands -------------------------------


def _academictransfer_card(anchor):
    best = None
    for parent in anchor.parents:
        if getattr(parent, "name", None) not in {"article", "li", "div"}:
            continue
        text = clean(parent.get_text(" | ", strip=True))
        if len(text) < 40:
            continue
        best = parent
        if re.search(r"\bDeadline\b|\bPublished\b", text, re.I):
            return parent
        if parent.name in {"article", "li"}:
            return parent
    return best or anchor.parent


def _title_from_job_slug(href: str) -> str:
    slug = urlparse(href).path.rstrip("/").split("/")[-1]
    return clean(re.sub(r"[-_]+", " ", slug))


def parse_academictransfer_listing(html: str, base_url: str = ACADEMICTRANSFER_URL) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a.get("href") or ""))
        m = re.search(r"/en/jobs/(\d+)/", href)
        if not m or m.group(1) in seen:
            continue
        card = _academictransfer_card(a)
        context = clean(card.get_text(" | ", strip=True)) if card else _block_text(a)
        title = clean(a.get_text(" ", strip=True))
        if len(title) < 5 and card:
            heading = card.find(["h2", "h3", "h4", "h5"])
            if heading:
                title = clean(heading.get_text(" ", strip=True))
        if len(title) < 5:
            title = _title_from_job_slug(href)
        if not title or title.lower() in {"save", "save job", "apply now", "read more"}:
            continue
        deadline_m = re.search(r"Deadline\s+([^|]+?)(?=\s*(?:\||Published|$))", context, re.I)
        city_m = re.search(r"Published\s+[^|]+?(?:\||\s{2,})([A-Z][\w .'-]{2,40})(?:\||$)", context)
        seen.add(m.group(1))
        out.append({
            "id": m.group(1),
            "title": title,
            "url": href,
            "deadline": clean(deadline_m.group(1)) if deadline_m else "",
            "city": clean(city_m.group(1)) if city_m else "",
            "context": context,
        })
    return out


def collect_academictransfer(*, max_jobs: int | None = 80, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    return _generic_collect(
        source_key="academictransfer",
        provider="AcademicTransfer",
        listing_url=ACADEMICTRANSFER_URL,
        parser=parse_academictransfer_listing,
        country_code="NL",
        country_name="Netherlands",
        source_language="en",
        max_jobs=max_jobs,
        enrich_detail=enrich_detail,
        session=session,
    )


# -------------------------------- Germany ---------------------------------

_ACADEMICS_FOREIGN = {
    "österreich": "AT", "austria": "AT", "wien": "AT", "vienna": "AT",
    "schweiz": "CH", "switzerland": "CH", "zürich": "CH", "zurich": "CH",
    "dänemark": "DK", "denmark": "DK", "odense": "DK",
    "usa": "US", "united states": "US", "kalifornien": "US", "california": "US",
    "niederlande": "NL", "netherlands": "NL",
    "belgien": "BE", "belgium": "BE",
    "frankreich": "FR", "france": "FR",
    "china": "CN", "hainan": "CN",
    "vereinigtes königreich": "GB", "united kingdom": "GB", "england": "GB",
    "italien": "IT", "italy": "IT",
    "spanien": "ES", "spain": "ES",
}

_ACADEMICS_COUNTRY_NAMES = {
    "DE": "Germany", "AT": "Austria", "CH": "Switzerland", "DK": "Denmark",
    "US": "United States", "NL": "Netherlands", "BE": "Belgium", "FR": "France",
    "CN": "China", "GB": "United Kingdom", "IT": "Italy", "ES": "Spain",
}


def infer_academics_country(context: str) -> str:
    text = clean(context).lower()
    for marker, code in _ACADEMICS_FOREIGN.items():
        if marker in text:
            return code
    return "DE"


def parse_academics_listing(html: str, base_url: str = ACADEMICS_URL) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a.get("href") or ""))
        if "/jobs/" not in href:
            continue
        m = re.search(r"-(\d{5,})(?:[/?#]|$)", href)
        if not m or m.group(1) in seen:
            continue
        title = clean(a.get_text(" ", strip=True))
        if not title:
            continue
        context = _block_text(a)
        code = infer_academics_country(context)
        seen.add(m.group(1))
        out.append({
            "id": m.group(1),
            "title": title,
            "url": href,
            "country_code": code,
            "country_name": _ACADEMICS_COUNTRY_NAMES.get(code),
            "context": context,
        })
    return out


def collect_academics(*, max_jobs: int | None = 100, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    return _generic_collect(
        source_key="academics_de",
        provider="academics.de",
        listing_url=ACADEMICS_URL,
        parser=parse_academics_listing,
        country_code=None,
        country_name=None,
        source_language="de",
        max_jobs=max_jobs,
        enrich_detail=enrich_detail,
        session=session,
    )


# -------------------------------- Ireland ---------------------------------

_UVI_RESERVED = {"about-us", "advertise-with-us", "faq", "contact-us", "privacy", "terms", "search", "institutions", "login", "candidate-info"}


def parse_university_vacancies_listing(html: str, base_url: str = UNIVERSITY_VACANCIES_URL) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a.get("href") or ""))
        parsed = urlparse(href)
        if parsed.netloc and "universityvacancies.com" not in parsed.netloc:
            continue
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if not parts or parts[0] in _UVI_RESERVED or parsed.path.startswith("/sites/"):
            continue
        if not parsed.path.startswith("/node/") and len(parts) < 2:
            continue
        title = clean(a.get_text(" ", strip=True))
        context = _block_text(a)
        if len(title) < 6 or title.lower() in {"apply", "read more", "view", "details"}:
            continue
        source_id = _stable_tail_id(href)
        if source_id in seen:
            continue
        seen.add(source_id)
        ref_m = re.search(r"\b(?:Reference|Ref(?:erence)?)[\s:#-]*([A-Z0-9-]{4,})", context, re.I)
        out.append({
            "id": ref_m.group(1) if ref_m else source_id,
            "title": title,
            "url": href,
            "context": context,
        })
    return out


def collect_university_vacancies(*, max_jobs: int | None = 80, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    return _generic_collect(
        source_key="university_vacancies_ie",
        provider="University Vacancies Ireland",
        listing_url=UNIVERSITY_VACANCIES_URL,
        parser=parse_university_vacancies_listing,
        country_code="IE",
        country_name="Ireland",
        source_language="en",
        max_jobs=max_jobs,
        enrich_detail=enrich_detail,
        session=session,
    )


# -------------------------------- France ----------------------------------


def parse_cnrs_listing(html: str, base_url: str = CNRS_URL) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a.get("href") or ""))
        text = clean(a.get_text(" ", strip=True))
        context = _block_text(a)
        if not re.search(r"post-?doc|postdoctor|chercheur", text + " " + context, re.I):
            continue
        if not re.search(r"Offre|offre|emploi|jobspec|Details|detail", href, re.I):
            continue
        source_id = _stable_tail_id(href)
        if source_id in seen:
            continue
        seen.add(source_id)
        out.append({"id": source_id, "title": text or context[:160], "url": href, "context": context})
    return out


def collect_cnrs(*, max_jobs: int | None = 80, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    return _generic_collect(
        source_key="cnrs_emploi",
        provider="CNRS Emploi",
        listing_url=CNRS_URL,
        parser=parse_cnrs_listing,
        country_code="FR",
        country_name="France",
        source_language="fr",
        max_jobs=max_jobs,
        enrich_detail=enrich_detail,
        session=session,
    )


# ------------------------------- Australia --------------------------------


def parse_uniroles_listing(html: str, base_url: str = UNIROLES_URL) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a.get("href") or ""))
        title = clean(a.get_text(" ", strip=True))
        context = _block_text(a)
        if not title or not re.search(r"job|vacan|position|detail", href, re.I):
            continue
        if title.lower() in {"view job details", "view details", "apply", "read more"}:
            block = a.find_parent(["article", "li", "div"])
            heading = block.find(["h2", "h3", "h4", "h5"]) if block else None
            title = clean(heading.get_text(" ", strip=True)) if heading else title
        if len(title) < 6:
            continue
        source_id = _stable_tail_id(href)
        if source_id in seen:
            continue
        seen.add(source_id)
        employer_m = re.search(
            r"Employer\s*:\s*(.+?)(?=\s*(?:\|\s*)?(?:Employment Type|Closing|$))",
            context,
            re.I,
        )
        deadline_m = re.search(
            r"Closing\s*:\s*(.+?)(?=\s*(?:\|\s*)?(?:Employer|Employment Type|$))",
            context,
            re.I,
        )
        out.append({
            "id": source_id,
            "title": title,
            "url": href,
            "institution": clean(employer_m.group(1)) if employer_m else "",
            "deadline": clean(deadline_m.group(1)) if deadline_m else "",
            "context": context,
        })
    return out


def collect_uniroles(*, max_jobs: int | None = 100, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    return _generic_collect(
        source_key="uniroles_au",
        provider="Uni Roles Australia",
        listing_url=UNIROLES_URL,
        parser=parse_uniroles_listing,
        country_code="AU",
        country_name="Australia",
        source_language="en",
        max_jobs=max_jobs,
        enrich_detail=enrich_detail,
        session=session,
    )


# -------------------------------- Austria ---------------------------------


def parse_innsbruck_listing(html: str, base_url: str = INNSBRUCK_URL) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a.get("href") or ""))
        m = re.search(r"(?:asg_id_in|job_id|id)=([0-9]+)", href, re.I)
        if not m:
            continue
        source_id = m.group(1)
        if source_id in seen:
            continue
        title = clean(a.get_text(" ", strip=True))
        context = _block_text(a)
        if len(title) < 5:
            continue
        if not re.search(r"assistant|postdoc|professor|research|wissenschaft|university|universit", title + " " + context, re.I):
            continue
        seen.add(source_id)
        deadline_m = re.search(r"(?:Closing date|Deadline|Bewerbungsfrist)\s*:?\s*([^|]+)", context, re.I)
        out.append({"id": source_id, "title": title, "url": href, "deadline": clean(deadline_m.group(1)) if deadline_m else "", "context": context})
    return out


def collect_innsbruck(*, max_jobs: int | None = 100, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    return _generic_collect(
        source_key="uibk",
        provider="University of Innsbruck",
        listing_url=INNSBRUCK_URL,
        parser=parse_innsbruck_listing,
        country_code="AT",
        country_name="Austria",
        source_language="de",
        max_jobs=max_jobs,
        enrich_detail=enrich_detail,
        session=session,
    )
