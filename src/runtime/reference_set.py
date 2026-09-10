from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROSTER_PATH = ROOT / "config" / "reference" / "stage7_reference_roster_v1.json"
MANIFEST_PATH = ROOT / "data" / "reference" / "stage7" / "reference_set_manifest_v1.json"
SCHEMA_PATH = ROOT / "schemas" / "reference_vacancy.schema.json"
CAPTURE_SCHEMA_PATH = ROOT / "schemas" / "reference_capture.schema.json"
CAPTURE_LOG_PATH = ROOT / "data" / "reference" / "stage7" / "reference_capture_log_v1.jsonl"
RECORDS_PATH = ROOT / "data" / "reference" / "stage7" / "reference_observations_v1.jsonl"

CORE_MARKETS = ("NL", "DE", "IE", "GB", "BE", "FR", "AU", "AT")


def load_reference_roster() -> dict[str, Any]:
    return json.loads(ROSTER_PATH.read_text(encoding="utf-8"))


def load_reference_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_reference_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _jsonl_record_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def build_reference_construction_status() -> dict[str, Any]:
    roster = load_reference_roster()
    manifest = load_reference_manifest()
    schema = load_reference_schema()
    capture_schema = json.loads(CAPTURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    sources = list(roster["sources"])

    countries = Counter(str(row["country_code"]) for row in sources)
    relations = Counter(str(row["relation_to_pipeline"]) for row in sources)
    source_ids = [str(row["reference_source_id"]) for row in sources]
    urls = [str(row["url"]) for row in sources]

    schema_properties = set(schema.get("properties", {}))
    forbidden_match_fields = {
        "pipeline_match_status",
        "pipeline_match_id",
        "pipeline_match_method",
        "matched_pipeline_url",
    }

    return {
        "version": 1,
        "stage": "7.2",
        "profile": "REFERENCE_SET_CONSTRUCTION_STATUS",
        "status": manifest["status"],
        "reference_source_count": len(sources),
        "country_source_counts": dict(sorted(countries.items())),
        "relation_counts": dict(sorted(relations.items())),
        "duplicate_source_id_count": len(source_ids) - len(set(source_ids)),
        "duplicate_url_count": len(urls) - len(set(urls)),
        "all_core_markets_have_two_sources": all(countries[code] == 2 for code in CORE_MARKETS),
        "core_market_count": len(CORE_MARKETS),
        "source_roster_frozen": bool(manifest["source_roster_frozen"]),
        "reference_set_frozen": bool(manifest["reference_set_frozen"]),
        "window": dict(manifest["window"]),
        "capture_policy": dict(manifest["capture_policy"]),
        "schema_required_field_count": len(schema.get("required", [])),
        "capture_schema_required_field_count": len(capture_schema.get("required", [])),
        "schema_forbidden_match_fields_present": sorted(forbidden_match_fields & schema_properties),
        "current_record_count": _jsonl_record_count(RECORDS_PATH),
        "current_capture_event_count": _jsonl_record_count(CAPTURE_LOG_PATH),
        "expected_source_day_captures": int(manifest["expected_source_day_captures"]),
        "completion_quality_gate": manifest["completion_quality_gate"],
        "stage7_2_done_condition": manifest["stage7_2_done_condition"],
        "next_action": manifest["next_action"],
    }
