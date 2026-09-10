from __future__ import annotations

from collections import Counter
from typing import Any

from src.runtime.structural_completeness import build_structural_completeness_checks

RESOLUTIONS = {
    ("UNWIRED_EXISTING_COLLECTOR", "uniroles_au"): {
        "classification": "CONFIRMED_STRUCTURAL_GAP",
        "evidence": [
            "src/sources/core/portals.py: collect_uniroles exists with source_key=uniroles_au and country_code=AU",
            "Stage 6.3: source_id uniroles_au is not wired into production",
        ],
        "disposition": "REGISTER_ONLY_DEFER_SOURCE_CHANGE_UNTIL_POST_RECALL_GAP_ANALYSIS",
    },
    ("UNRESOLVED_CONFIGURED_GEOGRAPHY", "jobs_ac_uk"): {
        "classification": "NOT_STRUCTURAL_GAP_RECALL_PENDING",
        "evidence": [
            "docs/runtime/JOBS_AC_UK_REPAIR.md: country is assigned from listing evidence rather than a blanket production country",
            "Stage 6.2: geography_mode=BOARD_NATIVE_UNFILTERED",
        ],
        "disposition": "DEFER_ACTUAL_COVERAGE_ASSESSMENT_TO_RECALL_MEASUREMENT",
    },
    ("UNRESOLVED_CONFIGURED_GEOGRAPHY", "academics_de"): {
        "classification": "NOT_STRUCTURAL_GAP_RECALL_PENDING",
        "evidence": [
            "src/sources/core/portals.py: academics.de infers country per listing",
            "Stage 6.2: geography_mode=LISTING_INFERRED_COUNTRY",
        ],
        "disposition": "DEFER_ACTUAL_COVERAGE_ASSESSMENT_TO_RECALL_MEASUREMENT",
    },
    ("UNRESOLVED_CONFIGURED_GEOGRAPHY", "ecss"): {
        "classification": "NOT_STRUCTURAL_GAP_RECALL_PENDING",
        "evidence": [
            "docs/runtime/ECSS_DVS_COVERAGE.md: ECSS is collected as a complete single listing page when uncapped",
            "Stage 6.2: geography_mode=LISTING_NATIVE",
        ],
        "disposition": "DEFER_ACTUAL_COVERAGE_ASSESSMENT_TO_RECALL_MEASUREMENT",
    },
    ("UNRESOLVED_CONFIGURED_GEOGRAPHY", "dvs"): {
        "classification": "NOT_STRUCTURAL_GAP_RECALL_PENDING",
        "evidence": [
            "docs/runtime/ECSS_DVS_COVERAGE.md: DVS is collected as a complete single listing page when uncapped",
            "Stage 6.2: geography_mode=LISTING_NATIVE",
        ],
        "disposition": "DEFER_ACTUAL_COVERAGE_ASSESSMENT_TO_RECALL_MEASUREMENT",
    },
    ("UNRESOLVED_CONFIGURED_GEOGRAPHY", "fens"): {
        "classification": "NOT_STRUCTURAL_GAP_RECALL_PENDING",
        "evidence": [
            "Stage 6.1: FENS is intentionally represented as a thematic listing-native source",
            "Stage 6.2: geography_mode=LISTING_NATIVE",
        ],
        "disposition": "DEFER_ACTUAL_COVERAGE_ASSESSMENT_TO_RECALL_MEASUREMENT",
    },
    ("ALTERNATE_COLLECTOR_IMPLEMENTATION", "cnrs_emploi"): {
        "classification": "NOT_GAP",
        "evidence": [
            "Stage 6.3: production already wires source_id cnrs_emploi through the dedicated CNRS module",
        ],
        "disposition": "NO_ACTION",
    },
    ("ALTERNATE_COLLECTOR_IMPLEMENTATION", "university_vacancies_ie"): {
        "classification": "NOT_GAP",
        "evidence": [
            "Stage 6.3: production already wires source_id university_vacancies_ie through the dedicated University Vacancies module",
        ],
        "disposition": "NO_ACTION",
    },
    ("SHARED_REPORT_KEY", "linkedin_mads"): {
        "classification": "NOT_GAP",
        "evidence": [
            "Stage 6.3: linkedin_australia and linkedin_europe intentionally share report_key linkedin_mads",
        ],
        "disposition": "NO_ACTION",
    },
}


def _resolution_key(finding: dict[str, Any]) -> tuple[str, str]:
    code = str(finding["code"])
    identifier = str(
        finding.get("source_id")
        or finding.get("report_key")
        or finding.get("country_code")
        or finding.get("shard_id")
        or ""
    )
    return code, identifier


def build_evidence_gap_register() -> dict[str, Any]:
    audit = build_structural_completeness_checks()
    entries: list[dict[str, Any]] = []

    for finding in audit["findings"]:
        key = _resolution_key(finding)
        resolution = RESOLUTIONS.get(key)
        if resolution is None:
            raise KeyError(f"No Stage 6.4 resolution for structural finding {key}")
        entries.append({
            "finding_code": finding["code"],
            "identifier": key[1],
            "classification": resolution["classification"],
            "severity": finding["severity"],
            "disposition": resolution["disposition"],
            "evidence": list(resolution["evidence"]),
            "structural_finding": finding,
        })

    classifications = Counter(entry["classification"] for entry in entries)
    confirmed = [
        entry for entry in entries
        if entry["classification"] == "CONFIRMED_STRUCTURAL_GAP"
    ]
    pending = [
        entry for entry in entries
        if entry["classification"] == "NOT_STRUCTURAL_GAP_RECALL_PENDING"
    ]
    not_gap = [
        entry for entry in entries
        if entry["classification"] == "NOT_GAP"
    ]

    return {
        "version": 1,
        "stage": "6.4",
        "profile": "EVIDENCE_BASED_GAP_REGISTER",
        "semantics": "REGISTER_ONLY_NO_SOURCE_CHANGE",
        "entry_count": len(entries),
        "classification_counts": dict(sorted(classifications.items())),
        "confirmed_structural_gap_count": len(confirmed),
        "recall_pending_count": len(pending),
        "not_gap_count": len(not_gap),
        "confirmed_structural_gap_ids": sorted(entry["identifier"] for entry in confirmed),
        "recall_pending_ids": sorted(entry["identifier"] for entry in pending),
        "not_gap_ids": sorted(entry["identifier"] for entry in not_gap),
        "entries": entries,
        "source_change_allowed": False,
        "next_decision_boundary": "AFTER_STAGE_7_RECALL_AND_STAGE_8_GAP_ANALYSIS",
    }
