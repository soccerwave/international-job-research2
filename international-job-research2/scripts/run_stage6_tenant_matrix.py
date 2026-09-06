from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sources.core import corehr, pageup, smartrecruiters, successfactors, workday

SCHEMA = json.loads((ROOT / "schemas" / "vacancy.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
GOOD_DETAIL = {"FULL", "PARTIAL"}

FAMILIES = [
    ("corehr", corehr.TENANTS, corehr.collect),
    ("pageup", pageup.TENANTS, pageup.collect),
    ("smartrecruiters", smartrecruiters.TENANTS, smartrecruiters.collect),
    ("successfactors", successfactors.TENANTS, successfactors.collect),
    ("workday", workday.TENANTS, workday.collect),
]


def check_row(family: str, tenant_key: str, rows):
    if not rows:
        raise AssertionError("live discovery returned zero records")
    row = rows[0]
    errors = list(VALIDATOR.iter_errors(row))
    if errors:
        raise AssertionError("schema: " + "; ".join(error.message for error in errors[:4]))
    detail_status = row["description"]["detail_status"]
    if detail_status not in GOOD_DETAIL:
        raise AssertionError(
            f"detail={detail_status}: {row['description'].get('detail_failure_reason')}"
        )
    return {
        "family": family,
        "tenant": tenant_key,
        "acceptance": "PASS",
        "sample_id": row["source"]["source_job_id"],
        "sample_title": row["position"]["title_raw"],
        "provider": row["source"]["provider"],
        "country_code": row["location"]["country_code"],
        "detail_status": detail_status,
    }


def main():
    results = []
    failures = []
    for family, tenants, collector in FAMILIES:
        for tenant_key in tenants:
            try:
                rows = collector(tenant_key=tenant_key, max_jobs=1, enrich_detail=True)
                results.append(check_row(family, tenant_key, rows))
            except Exception as exc:
                failure = {
                    "family": family,
                    "tenant": tenant_key,
                    "acceptance": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                results.append(failure)
                failures.append(failure)

    payload = {
        "status": "FAIL" if failures else "OK",
        "validation_profile": "STAGE6_ATS_TENANT_MATRIX_RC",
        "tenant_count": len(results),
        "pass_count": len(results) - len(failures),
        "failure_count": len(failures),
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
