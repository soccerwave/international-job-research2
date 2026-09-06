from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

from src.runtime.artifacts import write_shard_bundle
from src.runtime.contracts import ShardDiagnostic, ShardStatus, utc_now_iso
from src.sources.core import corehr, pageup, portals, smartrecruiters, successfactors, university_vacancies, workday
from src.sources.shared import academicpositions, dvs, ecss, euraxess, fens, jobs_ac_uk, linkedin_mads

ROOT = Path(__file__).resolve().parents[2]
import json

VACANCY_SCHEMA = json.loads((ROOT / "schemas" / "vacancy.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(VACANCY_SCHEMA)
PRODUCER_VERSION = "V0.10_PREPROD_RC1_CANDIDATE"

CORE_EUROPE_COUNTRIES = ("NL", "DE", "IE", "GB", "BE", "FR", "AT")
OPPORTUNISTIC_EUROPE_COUNTRIES = ("IT", "PT", "CZ", "PL", "LU")
LINKEDIN_EUROPE_QUERIES = (
    "postdoctoral researcher",
    "research fellow",
    "assistant professor",
    "lecturer",
    "research associate",
    "postdoctoral fellow",
)
LINKEDIN_AUSTRALIA_QUERIES = (
    "postdoctoral researcher",
    "research fellow",
    "lecturer",
    "research associate",
    "postdoctoral fellow",
)
JOBS_AC_UK_QUERIES = (
    "postdoctoral",
    "research fellow",
    "lecturer",
    "exercise",
    "neuroscience",
    "research associate",
    "postdoctoral fellow",
    "research scientist",
)
LINKEDIN_EUROPE_PARTITIONS = {
    "linkedin-europe-germany": ("Germany",),
    "linkedin-europe-west": ("Netherlands", "Ireland", "United Kingdom", "Belgium"),
    "linkedin-europe-france-austria": ("France", "Austria"),
    "linkedin-europe-opportunistic": ("Italy", "Portugal", "Czechia", "Poland", "Luxembourg"),
}


@dataclass(frozen=True)
class SourceCall:
    source_id: str
    report_key: str
    collector: Callable[[], list[dict[str, Any]]]


def _limit(default: int = 3) -> int:
    raw = str(os.environ.get("STAGE10_MAX_JOBS_PER_SOURCE") or default).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(1, min(value, 20))


def _linkedin_repo() -> str:
    repo = str(os.environ.get("AI_JOB_SEARCH_MADS_REPO") or "").strip()
    if not repo:
        raise RuntimeError("AI_JOB_SEARCH_MADS_REPO is required for LinkedIn Stage 10 shards")
    return repo


def _specs() -> dict[str, list[SourceCall]]:
    limit = _limit()
    all_europe = CORE_EUROPE_COUNTRIES + OPPORTUNISTIC_EUROPE_COUNTRIES
    specs = {
        "euraxess-europe": [
            SourceCall(
                "euraxess_europe", "euraxess",
                lambda: euraxess.collect(country_codes=all_europe, pages_per_country=1, max_jobs=max(limit * 2, 6), enrich_detail=True),
            )
        ],
        "academicpositions": [
            SourceCall(
                "academicpositions", "academicpositions",
                lambda: academicpositions.collect(country_codes=all_europe, max_pages_per_country=1, max_jobs=max(limit * 2, 6), enrich_detail=True),
            )
        ],
        "linkedin-australia": [
            SourceCall(
                "linkedin_australia", "linkedin_mads",
                lambda: linkedin_mads.collect(
                    locations=("Australia",),
                    queries=LINKEDIN_AUSTRALIA_QUERIES,
                    limit_per_search=3,
                    jobage_days=14,
                    max_jobs=max(limit, 4),
                    enrich_detail=True,
                    repo_path=_linkedin_repo(),
                ),
            )
        ],
        "uk-ireland-portals": [
            SourceCall(
                "jobs_ac_uk", "jobs_ac_uk",
                lambda: jobs_ac_uk.collect(
                    keywords=JOBS_AC_UK_QUERIES,
                    pages_per_query=1,
                    max_jobs=max(limit * 2, 6),
                    enrich_detail=True,
                ),
            ),
            SourceCall(
                "university_vacancies_ie", "university_vacancies_ie",
                lambda: university_vacancies.collect(max_jobs=max(limit, 4), enrich_detail=True),
            ),
        ],
        "thematic": [
            SourceCall("ecss", "ecss", lambda: ecss.collect(max_jobs=limit, enrich_detail=True)),
            SourceCall("dvs", "dvs", lambda: dvs.collect(max_jobs=limit, enrich_detail=True)),
            SourceCall("fens", "fens", lambda: fens.collect(max_pages=5, max_jobs=limit, enrich_detail=True)),
        ],
        "netherlands": [
            SourceCall("academictransfer", "academictransfer", lambda: portals.collect_academictransfer(max_jobs=max(limit, 4)))
        ],
        "germany-france-primary": [
            SourceCall("academics_de", "academics_de", lambda: portals.collect_academics(max_jobs=max(limit, 4))),
            SourceCall("cnrs_emploi", "cnrs_emploi", lambda: portals.collect_cnrs(max_jobs=max(limit, 4))),
        ],
        "corehr-ireland": [
            SourceCall(f"corehr_{tenant}", f"corehr_{tenant}", lambda tenant=tenant: corehr.collect(tenant_key=tenant, max_jobs=limit, enrich_detail=True))
            for tenant in corehr.TENANTS
        ],
        "successfactors-belgium-austria": [
            SourceCall(
                f"successfactors_{tenant}", f"successfactors_{tenant}",
                lambda tenant=tenant: successfactors.collect(tenant_key=tenant, max_jobs=limit, enrich_detail=True),
            )
            for tenant in successfactors.TENANTS
        ],
        "australia-pageup": [
            SourceCall(f"pageup_{tenant}", f"pageup_{tenant}", lambda tenant=tenant: pageup.collect(tenant_key=tenant, max_jobs=limit, enrich_detail=True))
            for tenant in pageup.TENANTS
        ],
        "australia-smartrecruiters": [
            SourceCall(
                f"smartrecruiters_{tenant}", f"smartrecruiters_{tenant}",
                lambda tenant=tenant: smartrecruiters.collect(tenant_key=tenant, max_jobs=limit, enrich_detail=True),
            )
            for tenant in smartrecruiters.TENANTS
        ],
        "australia-workday": [
            SourceCall(f"workday_{tenant}", f"workday_{tenant}", lambda tenant=tenant: workday.collect(tenant_key=tenant, max_jobs=limit, enrich_detail=True))
            for tenant in workday.TENANTS
        ],
        "austria-direct": [
            SourceCall("uibk", "uibk", lambda: portals.collect_innsbruck(max_jobs=max(limit, 4)))
        ],
    }
    for shard_id, locations in LINKEDIN_EUROPE_PARTITIONS.items():
        specs[shard_id] = [
            SourceCall(
                "linkedin_europe", "linkedin_mads",
                lambda locations=locations: linkedin_mads.collect(
                    locations=locations,
                    queries=LINKEDIN_EUROPE_QUERIES,
                    limit_per_search=2,
                    jobage_days=14,
                    max_jobs=max(limit * 2, 6),
                    enrich_detail=True,
                    repo_path=_linkedin_repo(),
                ),
            )
        ]
    return specs


SHARD_IDS = tuple(_specs().keys())


def _validate_rows(source_id: str, rows: list[dict[str, Any]]) -> None:
    for index, row in enumerate(rows):
        errors = list(VALIDATOR.iter_errors(row))
        if errors:
            raise RuntimeError(
                f"{source_id} schema validation failed at row {index}: "
                + "; ".join(error.message for error in errors[:4])
            )


def run_live_shard(*, run_id: str, shard_id: str, output_root: Path) -> ShardDiagnostic:
    specs = _specs()
    if shard_id not in specs:
        raise KeyError(f"Unknown Stage 10 shard: {shard_id}")

    started_at = utc_now_iso()
    started = time.monotonic()
    records: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    for spec in specs[shard_id]:
        source_started = time.monotonic()
        try:
            rows = spec.collector()
            _validate_rows(spec.source_id, rows)
            records.extend(rows)
            result_warnings = []
            if not rows:
                result_warnings.append("Zero observations in this low-volume shadow probe; not treated as closure or source failure.")
            source_results.append({
                "source_id": spec.source_id,
                "report_key": spec.report_key,
                "status": "OK",
                "records": len(rows),
                "elapsed_ms": int((time.monotonic() - source_started) * 1000),
                "warnings": result_warnings,
                "error": "",
            })
            warnings.extend(f"{spec.source_id}: {item}" for item in result_warnings)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            errors.append(f"{spec.source_id}: {message}")
            source_results.append({
                "source_id": spec.source_id,
                "report_key": spec.report_key,
                "status": "ERROR",
                "records": 0,
                "elapsed_ms": int((time.monotonic() - source_started) * 1000),
                "warnings": [],
                "error": message,
            })

    success_count = sum(item["status"] == "OK" for item in source_results)
    if success_count == len(source_results):
        status = ShardStatus.OK
    elif success_count:
        status = ShardStatus.PARTIAL
    else:
        status = ShardStatus.ERROR

    detail_attempted = sum(1 for row in records if str((row.get("description") or {}).get("detail_status") or "") != "NOT_ATTEMPTED")
    detail_succeeded = sum(1 for row in records if str((row.get("description") or {}).get("detail_status") or "") in {"FULL", "PARTIAL"})
    diagnostic = ShardDiagnostic(
        shard_id=shard_id,
        source_ids=[spec.source_id for spec in specs[shard_id]],
        status=status,
        started_at=started_at,
        finished_at=utc_now_iso(),
        elapsed_ms=int((time.monotonic() - started) * 1000),
        records_observed=len(records),
        records_emitted=len(records),
        detail_attempted=detail_attempted,
        detail_succeeded=detail_succeeded,
        warnings=warnings,
        errors=errors,
        metadata={"source_results": source_results, "shadow_probe": True},
    )
    write_shard_bundle(
        root=output_root,
        run_id=run_id,
        shard_id=shard_id,
        source_ids=[spec.source_id for spec in specs[shard_id]],
        records=records,
        diagnostic=diagnostic,
        producer_version=PRODUCER_VERSION,
    )
    return diagnostic
