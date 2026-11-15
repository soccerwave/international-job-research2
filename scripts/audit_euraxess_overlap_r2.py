"""Read-only EURAXESS reference-vs-R2-state overlap audit.

No R2 writes and no dump of R2 snapshots. Exact matches and possible
cross-source title matches are separate; this is not an end-to-end recall rate.
"""
from __future__ import annotations
from collections import defaultdict
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import unicodedata

from src.state.r2_store import R2StateStore

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "validation/euraxess_reference_2026-11-15.json"


def norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def state_indexes(state):
    by_alias = defaultdict(set)
    by_country = defaultdict(list)
    for state_id, entry in state.get("jobs", {}).items():
        for alias in entry.get("aliases") or []:
            if isinstance(alias, str):
                by_alias[alias.lower()].add(state_id)
        snap = entry.get("last_snapshot") or {}
        country = str(snap.get("country_code") or "").upper()
        if country and snap.get("title"):
            by_country[country].append((state_id, entry, snap))
    return by_alias, by_country


def reference_match(row, by_alias, by_country):
    url = row["url"].lower().rstrip("/")
    exact_ids = set(by_alias.get("source_id:euraxess:" + row["id"], ()))
    exact_ids.update(by_alias.get("url:" + url, ()))
    title = norm(row["title"])
    # Do not treat generic UCD level-1 titles as unique evidence.
    generic_title = title in {"ucd post doctoral research fellow level 1"}
    candidates = []
    for sid, entry, snap in by_country.get(row["country"], []):
        if sid in exact_ids:
            continue
        candidate = norm(snap.get("title"))
        similarity = SequenceMatcher(None, title, candidate).ratio()
        if similarity < 0.92:
            continue
        aliases = [a for a in entry.get("aliases") or [] if isinstance(a, str)]
        sources = sorted({a.split(":", 2)[1] for a in aliases if a.startswith("source_id:") and len(a.split(":", 2)) > 2})
        org = norm(snap.get("institution"))
        expected_org = norm(row["org"])
        # Institution must be comparable; acronym/brand ambiguity is retained as a candidate only.
        org_overlap = bool(org and expected_org and (org in expected_org or expected_org in org))
        candidates.append({
            "state_id": sid,
            "title": snap.get("title"),
            "institution": snap.get("institution"),
            "title_similarity": round(similarity, 3),
            "organization_compatible": org_overlap,
            "source_keys": sources,
            "first_seen": entry.get("first_seen_at"),
            "last_seen": entry.get("last_seen_at"),
        })
    candidates.sort(key=lambda x: (x["organization_compatible"], x["title_similarity"]), reverse=True)
    # A title-only match or generic postdoc title is never automatically a confirmed cross-source match.
    if exact_ids:
        status = "EXACT_EURAXESS_ID_IN_STATE"
    elif candidates:
        status = "CROSS_SOURCE_POSSIBLE_REQUIRES_ADJUDICATION"
    else:
        status = "NOT_MATCHED_IN_CURRENT_R2_STATE"
    return {
        "id": row["id"],
        "title": row["title"],
        "country": row["country"],
        "posted": row["date"],
        "cohort": row["cohort"],
        "priority": row["priority"],
        "reference_source": row["channel"],
        "url": row["url"],
        "status": status,
        "exact_euraxess_match_count": len(exact_ids),
        "cross_source_candidate_count": len(candidates),
        "generic_title_ambiguity": generic_title,
        "possible_cross_source_matches": candidates[:5],
    }


def main():
    source = json.loads(REFERENCE.read_text(encoding="utf-8"))
    loaded = R2StateStore.from_env().load_current(allow_missing=False)
    by_alias, by_country = state_indexes(loaded.state)
    results = [reference_match(row, by_alias, by_country) for row in source["reference"]]
    report = {
        "read_only": True,
        "state_generation": loaded.state.get("generation"),
        "state_job_count": len(loaded.state["jobs"]),
        "sampling_caution": source["sampling"],
        "interpretation": "State matches are capture evidence, not an overall recall rate. Unmatched current-state entries require archived raw shard and reporting review.",
        "results": results,
    }
    output = Path("euraxess-reference-vs-r2-state.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in results:
        print(f'{row["id"]} {row["priority"]} {row["status"]} candidates={row["cross_source_candidate_count"]}')
    print("AUDIT_STATE_GENERATION", report["state_generation"])
    print("AUDIT_RESULT_PATH", str(output))


if __name__ == "__main__":
    main()
