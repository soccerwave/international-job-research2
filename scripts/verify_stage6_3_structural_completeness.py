from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.structural_completeness import build_structural_completeness_checks


def main() -> int:
    audit = build_structural_completeness_checks()
    codes = [row["code"] for row in audit["findings"]]
    checks = {
        "structural_audit_semantics": audit["semantics"] == "STRUCTURAL_AUDIT_ONLY_NO_GAP_VERDICT",
        "all_target_countries_have_explicit_wiring": audit["target_countries_without_explicit_wiring"] == [],
        "all_registered_tenants_are_wired": audit["unwired_registered_tenant_count"] == 0,
        "all_linkedin_partitions_are_wired": audit["unwired_linkedin_partition_count"] == 0,
        "portal_surface_is_accounted": audit["portal_collector_surface_count"] == 6,
        "uniroles_unwired_collector_is_visible": any(
            row["code"] == "UNWIRED_EXISTING_COLLECTOR" and row.get("source_id") == "uniroles_au"
            for row in audit["findings"]
        ),
        "alternate_implementations_are_visible": sum(code == "ALTERNATE_COLLECTOR_IMPLEMENTATION" for code in codes) == 2,
        "unresolved_geography_is_preserved_for_review": audit["unresolved_geography_execution_count"] == 5,
        "shared_report_key_is_visible": audit["shared_report_key_count"] == 1,
        "no_gap_verdict_is_emitted": all("gap" not in row for row in audit["findings"]),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("Stage 6.3 structural completeness verification failed: " + ", ".join(failed))

    print(json.dumps({
        "status": "PASS",
        "profile": "STAGE_6_3_STRUCTURAL_COMPLETENESS",
        "checks": checks,
        "summary": {
            "target_country_count": len(audit["target_country_codes"]),
            "tenant_registry_count": audit["tenant_registry_count"],
            "linkedin_partition_count": audit["linkedin_partition_count"],
            "portal_collector_surface_count": audit["portal_collector_surface_count"],
            "review_finding_count": audit["review_finding_count"],
            "info_finding_count": audit["info_finding_count"],
            "unresolved_geography_execution_count": audit["unresolved_geography_execution_count"],
            "shared_report_key_count": audit["shared_report_key_count"],
        },
        "behavior": "READ_ONLY_STRUCTURAL_AUDIT",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
