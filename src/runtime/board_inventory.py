from __future__ import annotations

from collections import Counter
from typing import Any

from src.runtime.live_shards import (
    CORE_EUROPE_COUNTRIES,
    OPPORTUNISTIC_EUROPE_COUNTRIES,
    LINKEDIN_EUROPE_PARTITIONS,
)
from src.runtime.production_sources import production_source_map
from src.sources.core import corehr, pageup, smartrecruiters, successfactors, workday

COUNTRY_CODE_BY_LOCATION = {
    "Australia": "AU",
    "Austria": "AT",
    "Belgium": "BE",
    "Czechia": "CZ",
    "France": "FR",
    "Germany": "DE",
    "Ireland": "IE",
    "Italy": "IT",
    "Luxembourg": "LU",
    "Netherlands": "NL",
    "Poland": "PL",
    "Portugal": "PT",
    "United Kingdom": "GB",
}

STATIC_METADATA: dict[str, dict[str, Any]] = {
    "euraxess_europe": {
        "board_family": "EURAXESS",
        "board_kind": "MULTI_COUNTRY_AGGREGATOR",
        "configured_country_codes": list(CORE_EUROPE_COUNTRIES + OPPORTUNISTIC_EUROPE_COUNTRIES),
        "configured_locations": [],
        "geography_mode": "EXPLICIT_COUNTRY_FILTER",
        "institution": None,
    },
    "academicpositions": {
        "board_family": "Academic Positions",
        "board_kind": "MULTI_COUNTRY_AGGREGATOR",
        "configured_country_codes": list(CORE_EUROPE_COUNTRIES + OPPORTUNISTIC_EUROPE_COUNTRIES),
        "configured_locations": [],
        "geography_mode": "EXPLICIT_COUNTRY_FILTER",
        "institution": None,
    },
    "linkedin_australia": {
        "board_family": "LinkedIn",
        "board_kind": "SEARCH_PLATFORM",
        "configured_country_codes": ["AU"],
        "configured_locations": ["Australia"],
        "geography_mode": "EXPLICIT_LOCATION_SEARCH",
        "institution": None,
    },
    "jobs_ac_uk": {
        "board_family": "jobs.ac.uk",
        "board_kind": "ACADEMIC_JOB_BOARD",
        "configured_country_codes": [],
        "configured_locations": [],
        "geography_mode": "BOARD_NATIVE_UNFILTERED",
        "institution": None,
    },
    "university_vacancies_ie": {
        "board_family": "University Vacancies Ireland",
        "board_kind": "NATIONAL_ACADEMIC_PORTAL",
        "configured_country_codes": ["IE"],
        "configured_locations": [],
        "geography_mode": "FIXED_SOURCE_COUNTRY",
        "institution": None,
    },
    "ecss": {
        "board_family": "European College of Sport Science",
        "board_kind": "THEMATIC_JOB_BOARD",
        "configured_country_codes": [],
        "configured_locations": [],
        "geography_mode": "LISTING_NATIVE",
        "institution": None,
    },
    "dvs": {
        "board_family": "Deutsche Vereinigung für Sportwissenschaft",
        "board_kind": "THEMATIC_JOB_BOARD",
        "configured_country_codes": [],
        "configured_locations": [],
        "geography_mode": "LISTING_NATIVE",
        "institution": None,
    },
    "fens": {
        "board_family": "Federation of European Neuroscience Societies",
        "board_kind": "THEMATIC_JOB_BOARD",
        "configured_country_codes": [],
        "configured_locations": [],
        "geography_mode": "LISTING_NATIVE",
        "institution": None,
    },
    "academictransfer": {
        "board_family": "AcademicTransfer",
        "board_kind": "NATIONAL_ACADEMIC_PORTAL",
        "configured_country_codes": ["NL"],
        "configured_locations": [],
        "geography_mode": "FIXED_SOURCE_COUNTRY",
        "institution": None,
    },
    "academics_de": {
        "board_family": "academics.de",
        "board_kind": "ACADEMIC_JOB_BOARD",
        "configured_country_codes": [],
        "configured_locations": [],
        "geography_mode": "LISTING_INFERRED_COUNTRY",
        "institution": None,
    },
    "cnrs_emploi": {
        "board_family": "CNRS Emploi",
        "board_kind": "RESEARCH_ORGANISATION_PORTAL",
        "configured_country_codes": ["FR"],
        "configured_locations": [],
        "geography_mode": "FIXED_SOURCE_COUNTRY",
        "institution": None,
    },
    "uibk": {
        "board_family": "University of Innsbruck direct portal",
        "board_kind": "INSTITUTION_DIRECT",
        "configured_country_codes": ["AT"],
        "configured_locations": [],
        "geography_mode": "FIXED_SOURCE_COUNTRY",
        "institution": "University of Innsbruck",
    },
}


def _tenant_metadata(source_id: str) -> dict[str, Any] | None:
    families = (
        ("corehr_", corehr.TENANTS, "CoreHR"),
        ("successfactors_", successfactors.TENANTS, "SAP SuccessFactors"),
        ("pageup_", pageup.TENANTS, "PageUp"),
        ("smartrecruiters_", smartrecruiters.TENANTS, "SmartRecruiters"),
        ("workday_", workday.TENANTS, "Workday"),
    )
    for prefix, tenants, family in families:
        if not source_id.startswith(prefix):
            continue
        tenant_key = source_id[len(prefix):]
        tenant = tenants.get(tenant_key)
        if tenant is None:
            return None
        return {
            "board_family": family,
            "board_kind": "INSTITUTION_ATS",
            "configured_country_codes": [tenant.country_code],
            "configured_locations": [],
            "geography_mode": "FIXED_SOURCE_COUNTRY",
            "institution": tenant.provider,
            "tenant_key": tenant_key,
        }
    return None


def _linkedin_europe_metadata(shard_id: str) -> dict[str, Any]:
    locations = list(LINKEDIN_EUROPE_PARTITIONS[shard_id])
    return {
        "board_family": "LinkedIn",
        "board_kind": "SEARCH_PLATFORM",
        "configured_country_codes": [COUNTRY_CODE_BY_LOCATION[item] for item in locations],
        "configured_locations": locations,
        "geography_mode": "EXPLICIT_LOCATION_SEARCH",
        "institution": None,
    }


def build_current_board_inventory() -> dict[str, Any]:
    """Inventory current production wiring without executing any collector."""
    specs = production_source_map(limit=1)
    rows: list[dict[str, Any]] = []

    for shard_id in sorted(specs):
        for spec in specs[shard_id]:
            if spec.source_id == "linkedin_europe":
                metadata = _linkedin_europe_metadata(shard_id)
            else:
                metadata = _tenant_metadata(spec.source_id) or STATIC_METADATA.get(spec.source_id)
            if metadata is None:
                raise KeyError(f"No board inventory metadata for wired source: {spec.source_id}")

            row = {
                "shard_id": shard_id,
                "source_id": spec.source_id,
                "report_key": spec.report_key,
                **metadata,
            }
            row["institution_specific"] = bool(row.get("institution"))
            rows.append(row)

    configured_country_codes = sorted({
        code
        for row in rows
        for code in row.get("configured_country_codes", [])
    })
    institutions = sorted({
        str(row["institution"])
        for row in rows
        if row.get("institution")
    })
    board_families = sorted({str(row["board_family"]) for row in rows})
    unique_source_ids = sorted({str(row["source_id"]) for row in rows})
    unique_report_keys = sorted({str(row["report_key"]) for row in rows})

    return {
        "version": 1,
        "stage": "6.1",
        "profile": "CURRENT_PRODUCTION_BOARD_INVENTORY",
        "semantics": "CONFIGURED_WIRING_ONLY",
        "source_execution_count": len(rows),
        "production_shard_count": len(specs),
        "unique_source_id_count": len(unique_source_ids),
        "unique_report_key_count": len(unique_report_keys),
        "board_family_count": len(board_families),
        "institution_specific_source_count": sum(bool(row["institution_specific"]) for row in rows),
        "institution_count": len(institutions),
        "configured_country_count": len(configured_country_codes),
        "configured_country_codes": configured_country_codes,
        "board_families": board_families,
        "institutions": institutions,
        "source_ids": unique_source_ids,
        "report_keys": unique_report_keys,
        "board_kind_counts": dict(sorted(Counter(str(row["board_kind"]) for row in rows).items())),
        "geography_mode_counts": dict(sorted(Counter(str(row["geography_mode"]) for row in rows).items())),
        "executions": rows,
    }
