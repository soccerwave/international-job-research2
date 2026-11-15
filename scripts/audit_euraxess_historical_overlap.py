"""Read-only historical overlap assessment for EURAXESS against other R2 state entries.

Uses conservative matching to estimate *potential* replacement coverage, never
a verified EURAXESS recall rate. R2 stores source aliases and last snapshots,
not historical complete raw collections.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
import unicodedata

from src.state.r2_store import R2StateStore


def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in value if not unicodedata.combining(c)).lower()))


def sources_and_urls(entry):
    sources, urls = set(), set()
    for raw in entry.get("aliases") or ():
        if not isinstance(raw, str):
            continue
        a = raw.lower()
        if a.startswith("source_id:"):
            p = a.split(":", 2)
            if len(p) == 3:
                sources.add(p[1])
        if a.startswith("url:"):
            urls.add(a[4:].rstrip("/"))
    return sources, urls


def observed_near(eur, other, days=90):
    a, b = str(eur.get("first_seen_at") or "")[:10], str(other.get("first_seen_at") or "")[:10]
    try:
        return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).days) <= days
    except ValueError:
        return None


def make_index(jobs):
    # Multiple source identities on one state record, if any, are counted separately.
    other_by_title = defaultdict(list)
    other_by_url = defaultdict(list)
    eur = []
    for sid, entry in jobs.items():
        sources, urls = sources_and_urls(entry)
        snap = entry.get("last_snapshot") or {}
        title = norm(snap.get("title"))
        country = str(snap.get("country_code") or "").upper()
        x = {"state_id":sid, "entry":entry, "snap":snap, "sources":sources, "urls":urls,
             "title":title, "org":norm(snap.get("institution")), "country":country}
        if "euraxess" in sources:
            eur.append(x)
        else:
            if title and country:
                other_by_title[(country, title)].append(x)
            for url in urls:
                other_by_url[url].append(x)
    return eur, other_by_title, other_by_url


def classify(x, title_index, url_index):
    matches = {}
    for url in x["urls"]:
        for y in url_index.get(url, ()):
            if y["state_id"] != x["state_id"]:
                matches[y["state_id"]] = (y, "SHARED_EXACT_URL")
    for y in title_index.get((x["country"], x["title"]), ()):
        if y["state_id"] == x["state_id"]:
            continue
        org_match = bool(x["org"] and x["org"] == y["org"])
        # require reliable same institutional affiliation for conservative candidate
        if org_match:
            matches.setdefault(y["state_id"], (y, "EXACT_TITLE_ORG_COUNTRY"))
        else:
            matches.setdefault(y["state_id"], (y, "EXACT_TITLE_COUNTRY_ONLY"))
    ranked = sorted(matches.values(),key=lambda t:({"SHARED_EXACT_URL":0,"EXACT_TITLE_ORG_COUNTRY":1,"EXACT_TITLE_COUNTRY_ONLY":2}[t[1]],t[0]["state_id"]))
    exact_url = [y for y,method in ranked if method == "SHARED_EXACT_URL"]
    strict = [(y,method) for y,method in ranked if method in {"SHARED_EXACT_URL","EXACT_TITLE_ORG_COUNTRY"}]
    # Strict title/org match can still be different vacancies in repeat advertisements.
    strict_with_time = [(y,method) for y,method in strict if observed_near(x["entry"],y["entry"]) is not False]
    if exact_url:
        result = "URL_SHARED_STRONG_CANDIDATE"
    elif strict_with_time:
        result = "TITLE_ORG_COUNTRY_STRONG_CANDIDATE"
    elif strict:
        result = "TITLE_ORG_COUNTRY_DIFFERENT_PERIOD"
    elif ranked:
        result = "TITLE_COUNTRY_WEAK_CANDIDATE"
    else:
        result = "NO_CANDIDATE_IN_STATE"
    selected = strict_with_time or strict or ranked
    return result, selected[:5], ranked


def run(state):
    eur, title_index, url_index = make_index(state.get("jobs") or {})
    statuses, recommendations, months = Counter(), Counter(), Counter()
    by_priority = defaultdict(Counter)
    source_overlap = Counter()
    high_priority = []
    manual_review = []
    for x in eur:
        result, top, all_candidates = classify(x,title_index,url_index)
        statuses[result] += 1
        rec = str(x["snap"].get("recommendation") or "UNKNOWN").upper()
        recommendations[rec] += 1
        by_priority[rec][result] += 1
        months[str(x["entry"].get("first_seen_at") or "")[:7]] += 1
        # Candidate source counts are NOT verified duplicate counts; one EURAXESS job per source.
        for source in {source for y,method in all_candidates for source in y["sources"]}:
            source_overlap[source] += 1
        item = {
            "euraxess_state_id":x["state_id"],
            "euraxess_title":x["snap"].get("title"),
            "euraxess_institution":x["snap"].get("institution"),
            "country":x["country"],
            "first_seen":x["entry"].get("first_seen_at"),
            "last_seen":x["entry"].get("last_seen_at"),
            "stored_recommendation":rec,
            "match_status":result,
            "candidate_count":len(all_candidates),
            "top_candidates":[{"source_keys":sorted(y["sources"]),
                               "title":y["snap"].get("title"),
                               "institution":y["snap"].get("institution"),
                               "first_seen":y["entry"].get("first_seen_at"),
                               "last_seen":y["entry"].get("last_seen_at"),
                               "method":method,
                               "state_id":y["state_id"],
                               "first_seen_within_90_days":observed_near(x["entry"],y["entry"])}
                              for y,method in top],
        }
        if rec in {"STRONG_APPLY","APPLY"}:
            high_priority.append(item)
        elif result in {"URL_SHARED_STRONG_CANDIDATE","TITLE_ORG_COUNTRY_STRONG_CANDIDATE"}:
            if len(manual_review)<100:
                manual_review.append(item)
    return {
        "read_only":True,
        "state_generation":state.get("generation"),
        "state_job_count":len(state.get("jobs") or {}),
        "euraxess_count":len(eur),
        "first_seen_months":dict(sorted(months.items())),
        "status_counts":dict(statuses),
        "stored_recommendation_counts":dict(recommendations),
        "status_by_stored_recommendation":{k:dict(v) for k,v in sorted(by_priority.items())},
        "alternative_source_candidate_counts":dict(source_overlap.most_common()),
        "high_priority_euraxess_records":high_priority,
        "other_strong_candidate_review_sample":manual_review,
        "methodology_notes":[
            "The 2732 EURAXESS records were the ones the bot captured; it is NOT a random/full EURAXESS reference sample.",
            "A shared source URL is strong evidence of the same posting; matching title, institution and country remains provisional.",
            "Only current last_snapshot and source aliases survive, not all prior daily captured records or recommendations.",
            "Same state may have multiple source aliases; original canonicalization behavior can hide/remove evidence of overlap.",
            "Candidate coverage is an upper bound on replacement potential, NOT a proven recall measurement.",
            "Matching only exact normalized titles will miss legitimate title variants. Unique-looking is not necessarily unique.",
            "Captured-at time windows are first_seen dates, not actual publication dates.",
            "If institution is missing from EURAXESS, title-only candidates are weak.",
        ],
    }


def main():
    store = R2StateStore.from_env()
    loaded=store.load_current(allow_missing=False)
    report=run(loaded.state)
    Path("euraxess-historical-overlap.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("state_generation","state_job_count","euraxess_count","status_counts","stored_recommendation_counts","alternative_source_candidate_counts")},ensure_ascii=False))
    print("OUTPUT=euraxess-historical-overlap.json")


if __name__=="__main__":
    main()
