from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from src.runtime.board_inventory import build_current_board_inventory


def build_coverage_mapping() -> dict[str, Any]:
    """Map current configured production coverage without asserting completeness."""
    inventory = build_current_board_inventory()
    executions = inventory["executions"]

    country_rows: dict[str, dict[str, Any]] = {}
    country_to_executions: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in executions:
        for code in row.get("configured_country_codes", []):
            country_to_executions[str(code)].append(row)

    for code in sorted(country_to_executions):
        rows = country_to_executions[code]
        board_families = sorted({str(row["board_family"]) for row in rows})
        source_ids = sorted({str(row["source_id"]) for row in rows})
        shards = sorted({str(row["shard_id"]) for row in rows})
        institutions = sorted({
            str(row["institution"])
            for row in rows
            if row.get("institution")
        })
        geography_modes = sorted({str(row["geography_mode"]) for row in rows})
        country_rows[code] = {
            "country_code": code,
            "execution_count": len(rows),
            "unique_source_id_count": len(source_ids),
            "board_family_count": len(board_families),
            "board_families": board_families,
            "source_ids": source_ids,
            "shards": shards,
            "institution_count": len(institutions),
            "institutions": institutions,
            "geography_modes": geography_modes,
        }

    board_family_rows: dict[str, dict[str, Any]] = {}
    grouped_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in executions:
        grouped_family[str(row["board_family"])].append(row)

    for family in sorted(grouped_family):
        rows = grouped_family[family]
        board_family_rows[family] = {
            "board_family": family,
            "execution_count": len(rows),
            "source_ids": sorted({str(row["source_id"]) for row in rows}),
            "report_keys": sorted({str(row["report_key"]) for row in rows}),
            "shards": sorted({str(row["shard_id"]) for row in rows}),
            "configured_country_codes": sorted({
                str(code)
                for row in rows
                for code in row.get("configured_country_codes", [])
            }),
            "institutions": sorted({
                str(row["institution"])
                for row in rows
                if row.get("institution")
            }),
            "board_kinds": sorted({str(row["board_kind"]) for row in rows}),
            "geography_modes": sorted({str(row["geography_mode"]) for row in rows}),
        }

    institution_rows: dict[str, dict[str, Any]] = {}
    grouped_institution: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in executions:
        if row.get("institution"):
            grouped_institution[str(row["institution"])].append(row)

    for institution in sorted(grouped_institution):
        rows = grouped_institution[institution]
        institution_rows[institution] = {
            "institution": institution,
            "execution_count": len(rows),
            "source_ids": sorted({str(row["source_id"]) for row in rows}),
            "board_families": sorted({str(row["board_family"]) for row in rows}),
            "shards": sorted({str(row["shard_id"]) for row in rows}),
            "configured_country_codes": sorted({
                str(code)
                for row in rows
                for code in row.get("configured_country_codes", [])
            }),
        }

    unresolved_geography = [
        {
            "shard_id": str(row["shard_id"]),
            "source_id": str(row["source_id"]),
            "board_family": str(row["board_family"]),
            "board_kind": str(row["board_kind"]),
            "geography_mode": str(row["geography_mode"]),
        }
        for row in executions
        if not row.get("configured_country_codes")
    ]

    overlap_counts = Counter(
        int(row["board_family_count"])
        for row in country_rows.values()
    )

    return {
        "version": 1,
        "stage": "6.2",
        "profile": "CURRENT_CONFIGURED_COVERAGE_MAPPING",
        "semantics": "MAPPING_ONLY_NO_COMPLETENESS_JUDGEMENT",
        "country_count": len(country_rows),
        "country_execution_link_count": sum(row["execution_count"] for row in country_rows.values()),
        "country_rows": country_rows,
        "board_family_rows": board_family_rows,
        "institution_rows": institution_rows,
        "unresolved_geography_execution_count": len(unresolved_geography),
        "unresolved_geography_executions": unresolved_geography,
        "country_board_family_overlap_counts": {
            str(k): v for k, v in sorted(overlap_counts.items())
        },
        "all_explicit_countries_have_multi_board_overlap": all(
            row["board_family_count"] >= 2 for row in country_rows.values()
        ),
    }
