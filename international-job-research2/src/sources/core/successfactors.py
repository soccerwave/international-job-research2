from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.sources.shared.pagination import html_pages, reached
from src.sources.shared.common import clean, fetch_detail_text, make_record, make_session


@dataclass(frozen=True)
class SuccessFactorsTenant:
    key: str
    provider: str
    listing_url: str
    country_code: str
    country_name: str
    language: str = "en"
    additional_listing_urls: tuple[str, ...] = ()


TENANTS: dict[str, SuccessFactorsTenant] = {
    "ghent": SuccessFactorsTenant(
        "ghent",
        "Ghent University",
        "https://jobs.ugent.be/go/Research-staff/8809002/",
        "BE",
        "Belgium",
        "en",
        (
            "https://jobs.ugent.be/go/Assistant-academic-staff/8808502/",
            "https://jobs.ugent.be/go/Professorial-staff/8808902/",
        ),
    ),
    "vub": SuccessFactorsTenant("vub", "Vrije Universiteit Brussel", "https://jobs.vub.be/go/EN_ALL-JOBS/3775601/", "BE", "Belgium"),
    "uclouvain_science": SuccessFactorsTenant("uclouvain_science", "UCLouvain", "https://jobs.uclouvain.be/Personnelscientifique/go/UCLouvain-Personnel-scientifique/3272501/", "BE", "Belgium", "fr"),
    "univie_postdoc": SuccessFactorsTenant("univie_postdoc", "University of Vienna", "https://jobs.univie.ac.at/go/postdoctoral/8876901/", "AT", "Austria"),
}


def parse_listing(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a.get("href") or ""))
        if "/job/" not in href:
            continue
        m = re.search(r"/(\d{7,})(?:/|$)", href)
        if not m:
            nums = re.findall(r"(\d{5,})", href)
            if not nums:
                continue
            job_id = nums[-1]
        else:
            job_id = m.group(1)
        if job_id in seen:
            continue
        title = clean(a.get_text(" ", strip=True))
        if len(title) < 5:
            continue
        block = a.find_parent("tr") or a.find_parent(["li", "article", "div"]) or a.parent
        context = clean(block.get_text(" | ", strip=True)) if block else title
        if title.lower() in {"apply now", "view profile", "read more"}:
            continue
        seen.add(job_id)
        out.append({"id": job_id, "title": title, "url": href, "context": context})
    return out


def collect(*, tenant_key: str, max_jobs: int | None = 100, enrich_detail: bool = True, session=None) -> list[dict[str, Any]]:
    if tenant_key not in TENANTS:
        raise KeyError(f"Unknown SuccessFactors tenant: {tenant_key}")
    tenant = TENANTS[tenant_key]
    s = session or make_session()

    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for listing_url in (tenant.listing_url, *tenant.additional_listing_urls):
        for item in html_pages(s, listing_url, parse_listing, max_jobs=max_jobs):
            if item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            item = dict(item)
            item["listing_url"] = listing_url
            candidates.append(item)
            if reached(candidates, max_jobs):
                break
        if reached(candidates, max_jobs):
            break

    out: list[dict[str, Any]] = []
    for item in candidates[:max_jobs]:
        detail = None
        status = "NOT_ATTEMPTED"
        failure = None
        if enrich_detail:
            try:
                detail, status = fetch_detail_text(item["url"], s)
            except Exception as exc:
                status = "FETCH_FAILED"
                failure = f"{type(exc).__name__}: {exc}"
        out.append(
            make_record(
                source_key=f"successfactors_{tenant.key}",
                source_kind="ATS",
                provider=tenant.provider,
                source_job_id=item["id"],
                listing_url=item.get("listing_url") or tenant.listing_url,
                detail_url=item["url"],
                title=item["title"],
                institution=tenant.provider,
                country_code=tenant.country_code,
                country_name=tenant.country_name,
                full_jd=detail,
                detail_status=status,
                detail_failure_reason=failure,
                source_language=tenant.language,
                source_status="UNKNOWN",
                raw_extra={"tenant": tenant.key, "listing_context": item.get("context", "")},
            )
        )
    return out
