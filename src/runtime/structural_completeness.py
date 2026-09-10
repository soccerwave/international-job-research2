from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.runtime.board_inventory import build_current_board_inventory
from src.runtime.coverage_mapping import build_coverage_mapping
from src.runtime.live_shards import (
    CORE_EUROPE_COUNTRIES,
    OPPORTUNISTIC_EUROPE_COUNTRIES,
    LINKEDIN_EUROPE_PARTITIONS,
)
from src.sources.core import corehr, pageup, smartrecruiters, successfactors, workday

ROOT = Path(__file__).resolve().parents[2]
PORTALS_PATH = ROOT / "src" / "sources" / "core" / "portals.py"

TARGET_COUNTRY_CODES = tuple(
    sorted(set(CORE_EUROPE_COUNTRIES + OPPORTUNISTIC_EUROPE_COUNTRIES + ("AU",)))
)

TENANT_REGISTRIES = {
    "corehr": ("corehr_", corehr.TENANTS),
    "successfactors": ("successfactors_", successfactors.TENANTS),
    "pageup": ("pageup_", pageup.TENANTS),
    "smartrecruiters": ("smartrecruiters_", smartrecruiters.TENANTS),
    "workday": ("workday_", workday.TENANTS),
}


def _literal_source_key(call: ast.Call) -> str | None:
    for keyword in call.keywords:
        if keyword.arg != "source_key":
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


def _portal_collector_surface() -> list[dict[str, str]]:
    tree = ast.parse(PORTALS_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("collect_"):
            continue
        source_key = None
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Name) and func.id == "_generic_collect":
                source_key = _literal_source_key(child)
                if source_key:
                    break
        if source_key:
            rows.append({"collector": node.name, "source_id": source_key})
    return sorted(rows, key=lambda row: row["collector"])


def build_structural_completeness_checks() -> dict[str, Any]:
    """Audit current production structure without making completeness decisions."""
    inventory = build_current_board_inventory()
    mapping = build_coverage_mapping()
    wired_source_ids = set(inventory["source_ids"])

    target_country_rows = {
        code: mapping["country_rows"].get(code)
        for code in TARGET_COUNTRY_CODES
    }
    target_countries_without_explicit_wiring = sorted(
        code for code, row in target_country_rows.items() if not row
    )

    tenant_rows: list[dict[str, Any]] = []
    unwired_tenants: list[dict[str, str]] = []
    for family, (prefix, tenants) in TENANT_REGISTRIES.items():
        for tenant_key, tenant in sorted(tenants.items()):
            source_id = f"{prefix}{tenant_key}"
            wired = source_id in wired_source_ids
            row = {
                "family": family,
                "tenant_key": tenant_key,
                "source_id": source_id,
                "institution": tenant.provider,
                "country_code": tenant.country_code,
                "wired": wired,
            }
            tenant_rows.append(row)
            if not wired:
                unwired_tenants.append({
                    "family": family,
                    "tenant_key": tenant_key,
                    "source_id": source_id,
                    "institution": tenant.provider,
                })

    partition_rows: list[dict[str, Any]] = []
    unwired_linkedin_partitions: list[str] = []
    execution_shards = {row["shard_id"] for row in inventory["executions"]}
    for shard_id, locations in sorted(LINKEDIN_EUROPE_PARTITIONS.items()):
        wired = shard_id in execution_shards
        partition_rows.append({
            "shard_id": shard_id,
            "locations": list(locations),
            "wired": wired,
        })
        if not wired:
            unwired_linkedin_partitions.append(shard_id)

    portal_surface = _portal_collector_surface()
    portal_groups: dict[str, list[str]] = defaultdict(list)
    for row in portal_surface:
        portal_groups[row["source_id"]].append(row["collector"])

    portal_findings: list[dict[str, Any]] = []
    for source_id, collectors in sorted(portal_groups.items()):
        wired = source_id in wired_source_ids
        if not wired:
            portal_findings.append({
                "code": "UNWIRED_EXISTING_COLLECTOR",
                "severity": "REVIEW",
                "source_id": source_id,
                "collectors": sorted(collectors),
                "detail": "A concrete collector implementation exists in src/sources/core/portals.py but the source ID is not wired into production.",
            })
        elif len(collectors) >= 1 and source_id in {"cnrs_emploi", "university_vacancies_ie"}:
            portal_findings.append({
                "code": "ALTERNATE_COLLECTOR_IMPLEMENTATION",
                "severity": "INFO",
                "source_id": source_id,
                "collectors": sorted(collectors),
                "detail": "A portals.py implementation exists for a source ID that is wired through a dedicated production module.",
            })

    report_key_sources: dict[str, set[str]] = defaultdict(set)
    for row in inventory["executions"]:
        report_key_sources[str(row["report_key"])].add(str(row["source_id"]))
    shared_report_keys = [
        {
            "report_key": report_key,
            "source_ids": sorted(source_ids),
        }
        for report_key, source_ids in sorted(report_key_sources.items())
        if len(source_ids) > 1
    ]

    unresolved_geography = list(mapping["unresolved_geography_executions"])

    findings: list[dict[str, Any]] = []
    findings.extend(portal_findings)
    for row in unresolved_geography:
        findings.append({
            "code": "UNRESOLVED_CONFIGURED_GEOGRAPHY",
            "severity": "REVIEW",
            "source_id": row["source_id"],
            "shard_id": row["shard_id"],
            "detail": "Production wiring does not assign an explicit country list; actual listing coverage must be established from evidence.",
        })
    for row in shared_report_keys:
        findings.append({
            "code": "SHARED_REPORT_KEY",
            "severity": "INFO",
            "report_key": row["report_key"],
            "source_ids": row["source_ids"],
            "detail": "Multiple logical source IDs share one reporting key.",
        })
    for code in target_countries_without_explicit_wiring:
        findings.append({
            "code": "TARGET_COUNTRY_WITHOUT_EXPLICIT_WIRING",
            "severity": "REVIEW",
            "country_code": code,
            "detail": "A configured target country has no explicit production coverage row.",
        })
    for row in unwired_tenants:
        findings.append({
            "code": "UNWIRED_REGISTERED_TENANT",
            "severity": "REVIEW",
            **row,
            "detail": "A tenant registered in an active ATS module is not wired into production.",
        })
    for shard_id in unwired_linkedin_partitions:
        findings.append({
            "code": "UNWIRED_LINKEDIN_PARTITION",
            "severity": "REVIEW",
            "shard_id": shard_id,
            "detail": "A configured LinkedIn Europe partition is not present in production executions.",
        })

    review_findings = [row for row in findings if row["severity"] == "REVIEW"]
    info_findings = [row for row in findings if row["severity"] == "INFO"]

    return {
        "version": 1,
        "stage": "6.3",
        "profile": "STRUCTURAL_COMPLETENESS_CHECKS",
        "semantics": "STRUCTURAL_AUDIT_ONLY_NO_GAP_VERDICT",
        "target_country_codes": list(TARGET_COUNTRY_CODES),
        "target_countries_without_explicit_wiring": target_countries_without_explicit_wiring,
        "tenant_registry_count": len(tenant_rows),
        "unwired_registered_tenant_count": len(unwired_tenants),
        "tenant_rows": tenant_rows,
        "linkedin_partition_count": len(partition_rows),
        "unwired_linkedin_partition_count": len(unwired_linkedin_partitions),
        "linkedin_partition_rows": partition_rows,
        "portal_collector_surface_count": len(portal_surface),
        "portal_collector_surface": portal_surface,
        "shared_report_key_count": len(shared_report_keys),
        "shared_report_keys": shared_report_keys,
        "unresolved_geography_execution_count": len(unresolved_geography),
        "review_finding_count": len(review_findings),
        "info_finding_count": len(info_findings),
        "findings": findings,
        "status": "STRUCTURAL_FINDINGS_PRESENT" if review_findings else "NO_REVIEW_FINDINGS",
    }
