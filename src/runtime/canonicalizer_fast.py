from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from src.runtime import canonicalizer as legacy


def _features(record: dict[str, Any]) -> dict[str, Any]:
    source = legacy._source(record)
    position = legacy._position(record)
    description = legacy._description(record)
    title_raw = str(position.get("title_raw") or "")
    title_value = position.get("title_raw") or position.get("title_normalized")
    institution_value = position.get("institution_raw") or position.get("institution_normalized")
    detail_ok = legacy._detail_ok(record)
    shingles = (
        legacy._word_shingles(str(description.get("full_jd") or ""))
        if detail_ok
        else set()
    )
    return {
        "source_key": str(source.get("source_key") or "").strip().lower(),
        "source_job_id": str(source.get("source_job_id") or "").strip(),
        "country": str((record.get("location") or {}).get("country_code") or "").upper(),
        "urls": legacy._record_urls(record),
        "title": legacy._norm(title_value),
        "refs": legacy._reference_tokens(title_raw),
        "institution": legacy._norm(institution_value),
        "detail_ok": detail_ok,
        "shingles": shingles,
    }


def _same_vacancy_cached(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if (
        a["source_key"]
        and a["source_key"] == b["source_key"]
        and a["source_job_id"]
        and b["source_job_id"]
        and a["source_job_id"] != b["source_job_id"]
    ):
        return False

    if a["country"] and b["country"] and a["country"] != b["country"]:
        return False

    if a["urls"] & b["urls"]:
        return True

    title_a = a["title"]
    title_b = b["title"]
    if not title_a or not title_b:
        return False

    refs_a = a["refs"]
    refs_b = b["refs"]
    if refs_a and refs_b and refs_a.isdisjoint(refs_b):
        return False

    title_exact = title_a == title_b
    title_ratio = 1.0 if title_exact else SequenceMatcher(None, title_a, title_b).ratio()
    if not title_exact and title_ratio < 0.92:
        return False

    inst_a = a["institution"]
    inst_b = b["institution"]
    institution_close = False
    if inst_a and inst_b:
        institution_close = inst_a == inst_b or SequenceMatcher(None, inst_a, inst_b).ratio() >= 0.90

    both_resolved = bool(a["detail_ok"] and b["detail_ok"])
    containment = 0.0
    if both_resolved:
        shingles_a = a["shingles"]
        shingles_b = b["shingles"]
        if shingles_a and shingles_b:
            containment = len(shingles_a & shingles_b) / min(len(shingles_a), len(shingles_b))

    if not both_resolved:
        return bool(
            title_exact
            and refs_a
            and refs_b
            and not refs_a.isdisjoint(refs_b)
            and institution_close
        )

    if title_exact and institution_close and containment >= 0.55:
        return True
    if title_exact and containment >= 0.70:
        return True
    if title_ratio >= 0.96 and institution_close and containment >= 0.78:
        return True
    return False


def canonicalize_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    features = {id(record): _features(record) for record in records}
    clusters: list[list[dict[str, Any]]] = []

    for incoming in records:
        incoming_features = features[id(incoming)]
        match_index: int | None = None
        for index, cluster in enumerate(clusters):
            if any(
                _same_vacancy_cached(features[id(existing)], incoming_features)
                for existing in cluster
            ):
                match_index = index
                break
        if match_index is None:
            clusters.append([incoming])
        else:
            clusters[match_index].append(incoming)

    canonical = [legacy._merge_group(cluster) for cluster in clusters]
    cross_source_clusters = 0
    for cluster in clusters:
        source_keys = {
            str(legacy._source(record).get("source_key") or "")
            for record in cluster
        }
        if len(source_keys) > 1:
            cross_source_clusters += 1

    summary = {
        "input_records": len(records),
        "canonical_records": len(canonical),
        "duplicates_removed": len(records) - len(canonical),
        "merged_clusters": sum(1 for cluster in clusters if len(cluster) > 1),
        "cross_source_clusters": cross_source_clusters,
        "fail_open_unresolved_fuzzy_merge": "DISABLED",
    }
    return canonical, summary
