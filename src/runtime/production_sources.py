"""Production coverage policy, independent of the historical low-volume probe."""
from src.runtime.live_shards import (
    SourceCall,
    CORE_EUROPE_COUNTRIES,
    OPPORTUNISTIC_EUROPE_COUNTRIES,
    LINKEDIN_EUROPE_PARTITIONS,
    LINKEDIN_EUROPE_QUERIES,
    LINKEDIN_AUSTRALIA_QUERIES,
    JOBS_AC_UK_QUERIES,
    _linkedin_repo,
)
from src.sources.core import cnrs, corehr, pageup, portals, smartrecruiters, successfactors, university_vacancies, workday
from src.sources.shared import academicpositions, dvs, ecss, euraxess, fens, jobs_ac_uk, linkedin_mads


def production_source_map(limit=None) -> dict[str, list[SourceCall]]:
    all_europe = CORE_EUROPE_COUNTRIES + OPPORTUNISTIC_EUROPE_COUNTRIES
    specs = {
        "euraxess-europe": [
            SourceCall(
                "euraxess_europe", "euraxess",
                lambda: euraxess.collect(country_codes=all_europe, pages_per_country=None, max_jobs=limit, enrich_detail=True),
            )
        ],
        "academicpositions": [
            SourceCall(
                "academicpositions", "academicpositions",
                lambda: academicpositions.collect(country_codes=all_europe, max_pages_per_country=None, max_jobs=limit, enrich_detail=True),
            )
        ],
        "linkedin-australia": [
            SourceCall(
                "linkedin_australia", "linkedin_mads",
                lambda: linkedin_mads.collect(
                    locations=("Australia",),
                    queries=LINKEDIN_AUSTRALIA_QUERIES,
                    limit_per_search=None,
                    jobage_days=14,
                    max_jobs=limit,
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
                    pages_per_query=None,
                    max_jobs=limit,
                    enrich_detail=True,
                ),
            ),
            SourceCall(
                "university_vacancies_ie", "university_vacancies_ie",
                lambda: university_vacancies.collect(max_jobs=limit, enrich_detail=True),
            ),
        ],
        "thematic": [
            SourceCall("ecss", "ecss", lambda: ecss.collect(max_jobs=limit, enrich_detail=True)),
            SourceCall("dvs", "dvs", lambda: dvs.collect(max_jobs=limit, enrich_detail=True)),
            SourceCall("fens", "fens", lambda: fens.collect(max_pages=None, max_jobs=limit, enrich_detail=True)),
        ],
        "netherlands": [
            SourceCall("academictransfer", "academictransfer", lambda: portals.collect_academictransfer(max_jobs=limit))
        ],
        "germany-france-primary": [
            SourceCall("academics_de", "academics_de", lambda: portals.collect_academics(max_jobs=limit)),
            SourceCall("cnrs_emploi", "cnrs_emploi", lambda: cnrs.collect(max_jobs=limit)),
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
            SourceCall("uibk", "uibk", lambda: portals.collect_innsbruck(max_jobs=limit))
        ],
    }
    for shard_id, locations in LINKEDIN_EUROPE_PARTITIONS.items():
        specs[shard_id] = [
            SourceCall(
                "linkedin_europe", "linkedin_mads",
                lambda locations=locations: linkedin_mads.collect(
                    locations=locations,
                    queries=LINKEDIN_EUROPE_QUERIES,
                    limit_per_search=None,
                    jobage_days=14,
                    max_jobs=limit,
                    enrich_detail=True,
                    repo_path=_linkedin_repo(),
                ),
            )
        ]
    return specs
