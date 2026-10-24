"""Explicit domain-specific exclusion from paid Luna evaluation only.

Does not change collection, Rule routing, canonical storage, or historical evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from src.llm.production_shadow import ProductionShadowInputs

EXCLUDED_DOMAINS = frozenset({"alignerr.com"})


def _hostname(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or not raw.lower().startswith(("https://", "http://")):
        return ""
    try:
        return (urlparse(raw).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _matches_host(host: str) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in EXCLUDED_DOMAINS)


def is_excluded_from_paid_luna(job: dict[str, Any]) -> bool:
    """Use only the explicit source identity and verified source URLs, not title keywords."""
    source = job.get("source") or {}
    if not isinstance(source, dict):
        return False
    for key in ("listing_url", "detail_url", "source_url", "url"):
        if _matches_host(_hostname(source.get(key))):
            return True
    # Exact source identity, not substring matching of employers/titles.
    source_id = str(source.get("source_id") or source.get("source_name") or "").strip().casefold()
    if source_id == "alignerr":
        return True
    # Aggregators like LinkedIn use their own URLs for Alignerr adverts.
    # Match exact employer identity; never infer from title keywords.
    position = job.get("position") or {}
    if isinstance(position, dict):
        employer = str(
            position.get("institution_raw") or position.get("institution_normalized") or ""
        ).strip().casefold()
        if employer == "alignerr":
            return True
    return False


@dataclass(frozen=True)
class PaidLunaFilterResult:
    inputs: ProductionShadowInputs
    excluded_job_ids: tuple[str, ...]


def exclude_paid_luna_sources(inputs: ProductionShadowInputs) -> PaidLunaFilterResult:
    excluded = frozenset(
        str(job.get("canonical_id") or job.get("source_record_id") or "").strip()
        for job in inputs.jobs if is_excluded_from_paid_luna(job)
    )
    kept = tuple(
        job for job in inputs.jobs
        if str(job.get("canonical_id") or job.get("source_record_id") or "").strip() not in excluded
    )
    return PaidLunaFilterResult(
        inputs=ProductionShadowInputs(
            jobs=kept,
            main_job_ids=tuple(i for i in inputs.main_job_ids if i not in excluded),
            rescue_candidate_job_ids=tuple(i for i in inputs.rescue_candidate_job_ids if i not in excluded),
        ),
        excluded_job_ids=tuple(sorted(excluded)),
    )
