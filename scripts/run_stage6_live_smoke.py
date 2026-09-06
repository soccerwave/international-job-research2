from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sources.core import corehr, pageup, portals, smartrecruiters, successfactors, university_vacancies, workday
from src.sources.shared.common import make_session

SCHEMA = json.loads((ROOT / "schemas" / "vacancy.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
GOOD_DETAIL = {"FULL", "PARTIAL"}
VALIDATION_PROFILE = "STAGE6_FINAL_CORE_MARKET_COVERAGE"


def validate(name, rows, *, expected_country_code=None):
    if not rows:
        raise AssertionError(f"{name}: live discovery returned zero records")
    row = rows[0]
    errors = list(VALIDATOR.iter_errors(row))
    if errors:
        raise AssertionError(f"{name}: schema validation failed: " + "; ".join(e.message for e in errors[:5]))
    status = row["description"]["detail_status"]
    if status not in GOOD_DETAIL:
        raise AssertionError(
            f"{name}: detail retrieval failed: {status} / {row['description'].get('detail_failure_reason')}"
        )
    code = row["location"]["country_code"]
    if expected_country_code and code != expected_country_code:
        raise AssertionError(f"{name}: expected country_code={expected_country_code}, got {code}")
    return {
        "source": name,
        "records": len(rows),
        "sample_id": row["source"]["source_job_id"],
        "sample_title": row["position"]["title_raw"],
        "detail_status": status,
        "country_code": code,
        "provider": row["source"]["provider"],
        "source_kind": row["source"]["source_kind"],
        "acceptance": "PASS",
    }


def _xml_locs(text: str) -> list[str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    out = []
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1] == "loc" and elem.text:
            out.append(elem.text.strip())
    return out


def uniroles_sitemap_probe():
    s = make_session()
    sitemap_url = "https://uniroles.com.au/sitemap.xml"
    result = {
        "source": "uniroles_au",
        "acceptance": "DEFER_BLOCKED_ON_GITHUB_RUNNER",
        "reason": "Cloudflare blocks listing/detail HTTP from GitHub-hosted runner; sitemap probe pending",
        "sitemap_url": sitemap_url,
    }
    try:
        response = s.get(sitemap_url, timeout=(10, 45), allow_redirects=True)
        result.update({
            "sitemap_status": response.status_code,
            "sitemap_final_url": response.url,
            "sitemap_content_type": response.headers.get("content-type"),
        })
        if not response.ok:
            result["reason"] = f"Sitemap unavailable on runner: HTTP {response.status_code}; listing/detail already Cloudflare-blocked"
            return result

        locs = _xml_locs(response.text)
        result["root_loc_count"] = len(locs)
        job_urls = [url for url in locs if "/display-job/" in url]
        child_maps = [url for url in locs if url.lower().endswith((".xml", ".xml.gz"))]

        for child_url in child_maps[:8]:
            try:
                child = s.get(child_url, timeout=(10, 45), allow_redirects=True)
                if not child.ok:
                    continue
                for url in _xml_locs(child.text):
                    if "/display-job/" in url and url not in job_urls:
                        job_urls.append(url)
            except Exception:
                continue

        result["display_job_url_count"] = len(job_urls)
        if not job_urls:
            result["reason"] = "Allowed sitemap is readable but exposes no display-job URLs; search routes are robots-disallowed and HTML is Cloudflare-blocked"
            return result

        detail = s.get(job_urls[0], timeout=(10, 45), allow_redirects=True)
        result.update({
            "detail_status": detail.status_code,
            "detail_final_url": detail.url,
            "detail_server": detail.headers.get("server"),
            "detail_content_type": detail.headers.get("content-type"),
        })
        if detail.ok and "Just a moment" not in detail.text[:500]:
            result["acceptance"] = "SITEMAP_TRANSPORT_AVAILABLE_REQUIRES_ADAPTER"
            result["reason"] = "Sitemap discovery and direct detail are both readable on GitHub runner; implement sitemap-backed adapter before enabling UniRoles"
        else:
            result["reason"] = "Allowed sitemap may expose jobs, but direct job detail remains Cloudflare-blocked on GitHub runner; defer as non-operational backstop"
        return result
    except Exception as exc:
        result["reason"] = f"Sitemap probe failed: {type(exc).__name__}: {exc}; listing/detail already Cloudflare-blocked"
        return result


def main():
    probes = []
    probes.append(validate("academictransfer", portals.collect_academictransfer(max_jobs=1), expected_country_code="NL"))
    probes.append(validate("academics_de", portals.collect_academics(max_jobs=1)))
    probes.append(validate("university_vacancies_ie", university_vacancies.collect(max_jobs=1), expected_country_code="IE"))
    probes.append(validate("corehr_ucc", corehr.collect(tenant_key="ucc", max_jobs=1), expected_country_code="IE"))
    probes.append(validate("cnrs_emploi", portals.collect_cnrs(max_jobs=1), expected_country_code="FR"))
    probes.append(uniroles_sitemap_probe())
    probes.append(validate("pageup_monash", pageup.collect(tenant_key="monash", max_jobs=1), expected_country_code="AU"))
    probes.append(validate("smartrecruiters_western_sydney", smartrecruiters.collect(tenant_key="western_sydney", max_jobs=1), expected_country_code="AU"))
    probes.append(validate("successfactors_vub", successfactors.collect(tenant_key="vub", max_jobs=1), expected_country_code="BE"))
    probes.append(validate("workday_uq", workday.collect(tenant_key="uq", max_jobs=1), expected_country_code="AU"))
    probes.append(validate("uibk", portals.collect_innsbruck(max_jobs=1), expected_country_code="AT"))
    print(json.dumps({"status": "OK", "validation_profile": VALIDATION_PROFILE, "probes": probes}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
