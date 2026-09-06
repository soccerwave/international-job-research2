from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from src.sources.shared import academicpositions, dvs, ecss, euraxess, fens, jobs_ac_uk, linkedin_mads

GOOD_DETAIL={"FULL","PARTIAL"}
VALIDATION_PROFILE="STAGE5_FINAL_SHARED_COVERAGE"


def validate(name, rows, *, expected_country_code=None, require_country=False):
    if not rows:
        raise AssertionError(f"{name}: live discovery returned zero records")
    row=rows[0]
    status=row["description"]["detail_status"]
    if status not in GOOD_DETAIL:
        raise AssertionError(
            f"{name}: detail was not retrieved successfully: {status} / "
            f"{row['description'].get('detail_failure_reason')}"
        )
    country_code=row["location"]["country_code"]
    if expected_country_code and country_code != expected_country_code:
        raise AssertionError(f"{name}: expected country_code={expected_country_code}, got {country_code}")
    if require_country and not country_code:
        raise AssertionError(f"{name}: source evidence was expected to yield a country_code")
    return {
        "source":name,
        "records":len(rows),
        "sample_id":row["source"]["source_job_id"],
        "sample_title":row["position"]["title_raw"],
        "detail_status":status,
        "country_code":country_code,
    }


def main():
    probes=[]
    probes.append(validate(
        "euraxess",
        euraxess.collect(country_codes=("DE",),pages_per_country=1,max_jobs=1,enrich_detail=True),
        expected_country_code="DE",
    ))
    probes.append(validate(
        "academicpositions",
        academicpositions.collect(country_codes=("DE",),max_pages_per_country=1,max_jobs=1,enrich_detail=True),
        expected_country_code="DE",
    ))
    probes.append(validate(
        "jobs_ac_uk",
        jobs_ac_uk.collect(keywords=("neuroscience",),pages_per_query=1,max_jobs=1,enrich_detail=True),
        expected_country_code="GB",
    ))
    probes.append(validate("ecss",ecss.collect(max_jobs=1,enrich_detail=True),require_country=True))
    probes.append(validate("dvs",dvs.collect(max_jobs=1,enrich_detail=True),require_country=True))
    probes.append(validate("fens",fens.collect(max_pages=5,max_jobs=1,enrich_detail=True),require_country=True))

    mads=os.environ.get("AI_JOB_SEARCH_MADS_REPO")
    if not mads:
        raise AssertionError("AI_JOB_SEARCH_MADS_REPO is required for LinkedIn live probe")
    probes.append(validate(
        "linkedin",
        linkedin_mads.collect(
            locations=("Germany",),queries=("postdoctoral researcher",),limit_per_search=1,
            jobage_days=30,max_jobs=1,enrich_detail=True,repo_path=mads,
        ),
        expected_country_code="DE",
    ))

    print(json.dumps({"status":"OK","validation_profile":VALIDATION_PROFILE,"probes":probes},ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
