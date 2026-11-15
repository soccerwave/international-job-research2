"""Non-mutating feasibility audit of historical EURAXESS records in R2.

Outputs aggregate statistics only. Does not write to R2 or dump state. The
persistent state is not the historical raw listing archive.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import unicodedata

from src.state.r2_store import R2StateStore


def normalized(text):
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def safe_day(s):
    return str(s or "")[:10]


def aliases_of(entry):
    return [x.lower() for x in (entry.get("aliases") or []) if isinstance(x, str)]


def source_ids(entry):
    result = set()
    for alias in aliases_of(entry):
        if alias.startswith("source_id:"):
            segments = alias.split(":", 2)
            if len(segments) == 3:
                result.add(segments[1])
    return result


def summarize_state(state):
    jobs = state.get("jobs") or {}
    by_source = Counter()
    eur_entries = []
    others_by_country = defaultdict(list)
    for sid, entry in jobs.items():
        sources = source_ids(entry)
        for key in sources:
            by_source[key] += 1
        snapshot = entry.get("last_snapshot") or {}
        country = str(snapshot.get("country_code") or "").upper()
        if "euraxess" in sources:
            eur_entries.append((sid, entry, snapshot, sources))
        else:
            if country and normalized(snapshot.get("title")):
                others_by_country[country].append((sid, entry, snapshot, sources))
    eur_country = Counter()
    eur_first_month = Counter()
    eur_last_month = Counter()
    eur_reco = Counter()
    same_entry_multi_source = Counter()
    similar_title_candidates = 0
    compatible_org_candidates = 0
    unique_relevant_titles = Counter()
    for sid, entry, snapshot, sources in eur_entries:
        country = str(snapshot.get("country_code") or "").upper() or "UNKNOWN"
        eur_country[country] += 1
        eur_first_month[safe_day(entry.get("first_seen_at"))[:7]] += 1
        eur_last_month[safe_day(entry.get("last_seen_at"))[:7]] += 1
        eur_reco[str(snapshot.get("recommendation") or "UNKNOWN")] += 1
        if len(sources) > 1:
            for other in sources - {"euraxess"}:
                same_entry_multi_source[other] += 1
        title = normalized(snapshot.get("title"))
        org = normalized(snapshot.get("institution"))
        if not title:
            continue
        if any(t in title for t in ["exercise", "neurosc", "brain", "psycholog", "cognit", "sport", "physical activity", "stress"]):
            unique_relevant_titles[title] += 1
        # Exact normalized title is a candidate only; never claim a verified cross-source duplicate.
        candidates = [(other_entry, other_snap) for _, other_entry, other_snap, _ in others_by_country.get(country, []) if normalized(other_snap.get("title")) == title]
        if candidates:
            similar_title_candidates += 1
            if org and any((normalized(osnap.get("institution")) == org) for _, osnap in candidates):
                compatible_org_candidates += 1

    return {
        "state_generation": state.get("generation"),
        "state_total_jobs": len(jobs),
        "records_with_euraxess_source_id": len(eur_entries),
        "euraxess_first_seen_by_month": dict(sorted(eur_first_month.items())),
        "euraxess_last_seen_by_month": dict(sorted(eur_last_month.items())),
        "euraxess_by_country": dict(eur_country.most_common()),
        "euraxess_by_stored_recommendation": dict(eur_reco.most_common()),
        "euraxess_entries_also_with_other_source_id": sum(1 for _, _, _, ss in eur_entries if len(ss) > 1),
        "euraxess_other_source_keys_on_same_entry": dict(same_entry_multi_source),
        "euraxess_titles_with_exact_title_match_in_another_entry_same_country": similar_title_candidates,
        "euraxess_titles_with_exact_title_and_org_match_in_another_entry_same_country": compatible_org_candidates,
        "potentially_relevant_euraxess_keyword_title_count": sum(unique_relevant_titles.values()),
        "all_source_id_counts_top25": dict(by_source.most_common(25)),
    }


def list_inventory(store):
    client, bucket = store.client, store.bucket
    categories = {
        "state/current/": [],
        "state/backups/": [],
        "state/bootstrap/": [],
        "control-plane/runs/": [],
        "llm/reports/runs/": [],
    }
    for prefix in categories:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                categories[prefix].append({
                    "key": obj["Key"],
                    "bytes": int(obj.get("Size") or 0),
                    "modified": str(obj.get("LastModified") or ""),
                })
    result = {}
    for prefix, objects in categories.items():
        suffixes = Counter(o["key"].rsplit("/", 1)[-1] for o in objects)
        result[prefix] = {
            "object_count": len(objects),
            "bytes_total": sum(o["bytes"] for o in objects),
            "earliest_modified": min((o["modified"] for o in objects), default=None),
            "latest_modified": max((o["modified"] for o in objects), default=None),
            "top_names": dict(suffixes.most_common(8)),
        }
    return result, categories


def main():
    store = R2StateStore.from_env()
    inventory, objects = list_inventory(store)
    current = store.load_current(allow_missing=False).state
    current_summary = summarize_state(current)
    backups = sorted(objects["state/backups/"], key=lambda x: x["key"])
    historical = []
    # At most two older generations, to limit memory and read cost.
    for meta in backups[:1] + backups[-1:]:
        if historical and historical[-1]["key"] == meta["key"]:
            continue
        data = json.loads(store.client.get_object(Bucket=store.bucket, Key=meta["key"])["Body"].read().decode("utf-8"))
        info = summarize_state(data)
        historical.append({"key": meta["key"], "generation": info["state_generation"],
                           "state_total_jobs": info["state_total_jobs"],
                           "records_with_euraxess_source_id": info["records_with_euraxess_source_id"],
                           "euraxess_first_seen_by_month": info["euraxess_first_seen_by_month"]})
        del data
    report = {
        "read_only": True,
        "interpretation": "State aliases and last snapshot indicate retained source identity, NOT full raw descriptions or per-day capture. Historic backups may be truncated by retention. Title comparisons are ONLY candidate overlaps.",
        "inventory": inventory,
        "current": current_summary,
        "historical_sample": historical,
        "decision_hints": {
            "has_euraxess_in_state": current_summary["records_with_euraxess_source_id"] > 0,
            "has_backup_generations": inventory["state/backups/"]["object_count"] > 0,
            "has_shard_archive_in_r2_inventory": False,
            "source_note": "No state/shards prefix searched: raw shard artifacts are held in Github Actions, not demonstrated as R2 history.",
        },
    }
    out = Path("euraxess-r2-feasibility.json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "R2_current_generation": current_summary["state_generation"],
        "R2_current_state_jobs": current_summary["state_total_jobs"],
        "R2_euraxess_persisted": current_summary["records_with_euraxess_source_id"],
        "R2_backups": inventory["state/backups/"]["object_count"],
        "R2_control_plane_objects": inventory["control-plane/runs/"]["object_count"],
        "R2_potential_exact_title_org_candidate_matches": current_summary["euraxess_titles_with_exact_title_and_org_match_in_another_entry_same_country"],
        "report": str(out),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
