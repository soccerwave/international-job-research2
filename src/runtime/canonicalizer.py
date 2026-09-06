from __future__ import annotations

import copy
import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

GOOD_DETAIL = {"FULL", "PARTIAL"}
IDENTITY_QUERY_KEYS = {
    "id", "jobid", "job_id", "job-id", "vacancyid", "vacancy_id",
    "offerid", "offer_id", "positionid", "position_id", "requisitionid",
    "requisition_id", "reqid", "req_id", "p_recruitment_id",
}
SOURCE_KIND_PRIORITY = {
    "DIRECT_INSTITUTION": 0,
    "NATIONAL_PORTAL": 1,
    "ATS": 2,
    "THEMATIC_PORTAL": 3,
    "SHARED_AGGREGATOR": 4,
    "LINKEDIN": 5,
}


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _source(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("source")
    return value if isinstance(value, dict) else {}


def _position(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("position")
    return value if isinstance(value, dict) else {}


def _description(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("description")
    return value if isinstance(value, dict) else {}


def _detail_ok(record: dict[str, Any]) -> bool:
    desc = _description(record)
    return str(desc.get("detail_status") or "").upper() in GOOD_DETAIL and bool(str(desc.get("full_jd") or "").strip())


def _normalized_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.lower().rstrip("/")
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = f"{host}:{port}" if port else host
    path = re.sub(r"/{2,}", "/", parts.path or "/").rstrip("/") or "/"
    identity_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        if key.lower() in IDENTITY_QUERY_KEYS and str(value).strip():
            identity_pairs.append((key.lower(), str(value).strip().lower()))
    identity_pairs.sort()
    query = urlencode(identity_pairs)
    fragment = ""
    for pattern in (
        r"(?:^|/)job/(\d+)(?:$|[/?])",
        r"(?:^|/)jobs/(\d+)(?:$|[/?])",
        r"(?:^|/)ver-oferta/(\d+)(?:$|[/?])",
    ):
        match = re.search(pattern, parts.fragment or "", re.I)
        if match:
            fragment = "/" + match.group(0).strip("/")
            break
    return urlunsplit((scheme, netloc, path + fragment, query, "")).rstrip("/")


def _record_urls(record: dict[str, Any]) -> set[str]:
    source = _source(record)
    return {
        url for url in (
            _normalized_url(source.get("detail_url")),
            _normalized_url(source.get("apply_url")),
            _normalized_url(source.get("listing_url")),
        ) if url
    }


def _word_shingles(text: str, size: int = 5) -> set[tuple[str, ...]]:
    words = _norm(text).split()
    if len(words) < size:
        return set()
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}


def _detail_containment(a: dict[str, Any], b: dict[str, Any]) -> float:
    if not (_detail_ok(a) and _detail_ok(b)):
        return 0.0
    sa = _word_shingles(str(_description(a).get("full_jd") or ""))
    sb = _word_shingles(str(_description(b).get("full_jd") or ""))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def _reference_tokens(title: str) -> set[str]:
    raw = str(title or "").upper()
    patterns = [
        r"\b\d{2,4}[/-]\d{2,4}(?:[-_/][A-Z0-9]{1,12})+\b",
        r"\b[A-Z]{2,12}\d{2,4}[/-]\d{2,4}(?:[-_/][A-Z0-9]{1,12})*\b",
        r"\b(?:REF(?:ERENCE)?[.: _-]*)[A-Z0-9][A-Z0-9/_-]{3,}\b",
    ]
    out: set[str] = set()
    for pattern in patterns:
        for token in re.findall(pattern, raw):
            out.add(re.sub(r"\s+", "", token))
    return out


def _country_compatible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ca = str((a.get("location") or {}).get("country_code") or "").upper()
    cb = str((b.get("location") or {}).get("country_code") or "").upper()
    return not (ca and cb and ca != cb)


def _same_source_distinct_ids(a: dict[str, Any], b: dict[str, Any]) -> bool:
    sa, sb = _source(a), _source(b)
    key_a = str(sa.get("source_key") or "").strip().lower()
    key_b = str(sb.get("source_key") or "").strip().lower()
    id_a = str(sa.get("source_job_id") or "").strip()
    id_b = str(sb.get("source_job_id") or "").strip()
    return bool(key_a and key_a == key_b and id_a and id_b and id_a != id_b)


def _same_vacancy(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if _same_source_distinct_ids(a, b) or not _country_compatible(a, b):
        return False

    if _record_urls(a) & _record_urls(b):
        return True

    pa, pb = _position(a), _position(b)
    title_a = _norm(pa.get("title_raw") or pa.get("title_normalized"))
    title_b = _norm(pb.get("title_raw") or pb.get("title_normalized"))
    if not title_a or not title_b:
        return False

    refs_a = _reference_tokens(str(pa.get("title_raw") or ""))
    refs_b = _reference_tokens(str(pb.get("title_raw") or ""))
    if refs_a and refs_b and refs_a.isdisjoint(refs_b):
        return False

    title_exact = title_a == title_b
    title_ratio = SequenceMatcher(None, title_a, title_b).ratio()
    if not title_exact and title_ratio < 0.92:
        return False

    inst_a = _norm(pa.get("institution_raw") or pa.get("institution_normalized"))
    inst_b = _norm(pb.get("institution_raw") or pb.get("institution_normalized"))
    institution_close = False
    if inst_a and inst_b:
        institution_close = inst_a == inst_b or SequenceMatcher(None, inst_a, inst_b).ratio() >= 0.90

    both_resolved = _detail_ok(a) and _detail_ok(b)
    containment = _detail_containment(a, b) if both_resolved else 0.0

    # Exact URL above is sufficient. Otherwise unresolved records are deliberately not
    # fuzzily collapsed merely because title/institution match. Duplicate visibility is
    # safer than hiding a parallel vacancy when Full JD evidence is incomplete.
    if not both_resolved:
        return bool(title_exact and refs_a and refs_b and not refs_a.isdisjoint(refs_b) and institution_close)

    if title_exact and institution_close and containment >= 0.55:
        return True
    if title_exact and containment >= 0.70:
        return True
    if title_ratio >= 0.96 and institution_close and containment >= 0.78:
        return True
    return False


def _anchor_rank(record: dict[str, Any]) -> tuple[int, str, str, str]:
    source = _source(record)
    kind = str(source.get("source_kind") or "").upper()
    return (
        SOURCE_KIND_PRIORITY.get(kind, 99),
        _norm(source.get("source_key")),
        _norm(source.get("source_job_id")),
        _norm(record.get("source_record_id")),
    )


def _quality(record: dict[str, Any]) -> tuple[int, int, int]:
    desc = _description(record)
    detail = str(desc.get("full_jd") or "").strip()
    metadata = 0
    for section, keys in (
        (record.get("position") or {}, ("institution_raw", "department", "role_family", "role_level")),
        (record.get("location") or {}, ("country_code", "city")),
        (record.get("dates") or {}, ("deadline_at", "deadline_text")),
        (record.get("contract") or {}, ("term_type", "duration_months", "fte")),
    ):
        metadata += sum(value not in {None, "", "UNKNOWN"} for value in (section.get(key) for key in keys))
    return (1 if _detail_ok(record) else 0, len(detail), metadata)


def _fill_missing(target: dict[str, Any], other: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        current = target.get(key)
        incoming = other.get(key)
        if current in {None, "", "UNKNOWN"} and incoming not in {None, "", "UNKNOWN"}:
            target[key] = copy.deepcopy(incoming)


def _merge_requirements(records: list[dict[str, Any]], base: dict[str, Any]) -> None:
    req = base.setdefault("requirements", {})
    scalar_keys = (
        "phd_requirement", "degree_text", "years_postdoc", "work_rights_text", "sponsorship_text",
        "professional_registration_text", "teaching_requirement_text",
    )
    for record in sorted(records, key=_quality, reverse=True):
        incoming = record.get("requirements") or {}
        _fill_missing(req, incoming, scalar_keys)
        for key in ("degree_fields", "methods_required", "methods_preferred"):
            merged = list(req.get(key) or [])
            for item in incoming.get(key) or []:
                if item not in merged:
                    merged.append(copy.deepcopy(item))
            req[key] = merged
        merged_lang = list(req.get("language_requirements") or [])
        seen = {str(item) for item in merged_lang}
        for item in incoming.get("language_requirements") or []:
            marker = str(item)
            if marker not in seen:
                seen.add(marker)
                merged_lang.append(copy.deepcopy(item))
        req["language_requirements"] = merged_lang


def _merge_classification(records: list[dict[str, Any]], base: dict[str, Any]) -> None:
    best = max(records, key=_quality)
    best_class = copy.deepcopy(best.get("classification") or {})
    current = base.setdefault("classification", {})
    blockers: list[str] = []
    reviews: list[str] = []
    for record in records:
        cls = record.get("classification") or {}
        for code in cls.get("blocker_codes") or []:
            if code not in blockers:
                blockers.append(code)
        for code in cls.get("review_codes") or []:
            if code not in reviews:
                reviews.append(code)
    if _detail_ok(best):
        reviews = [code for code in reviews if "DETAIL" not in str(code).upper() and "FULL_JD" not in str(code).upper()]
    _fill_missing(current, best_class, ("market_tier", "role_policy_status"))
    current["blocker_codes"] = blockers
    current["review_codes"] = reviews
    if blockers:
        current["pre_evaluation_disposition"] = "POLICY_SKIP"
    elif not _detail_ok(best):
        current["pre_evaluation_disposition"] = "NEEDS_DETAIL_REVIEW"
    elif reviews:
        current["pre_evaluation_disposition"] = "POLICY_REVIEW"
    else:
        current["pre_evaluation_disposition"] = "ELIGIBLE_FOR_EVALUATION"


def _canonical_id(anchor: dict[str, Any]) -> str:
    source = _source(anchor)
    source_key = _norm(source.get("source_key")).replace(" ", "_")
    source_job_id = str(source.get("source_job_id") or "").strip().lower()
    source_record_id = str(anchor.get("source_record_id") or "").strip().lower()
    seed = f"source_id:{source_key}:{source_job_id}" if source_key and source_job_id else f"source_record:{source_key}:{source_record_id}"
    return "vac_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]


def _merge_group(records: list[dict[str, Any]]) -> dict[str, Any]:
    anchor = min(records, key=_anchor_rank)
    base = copy.deepcopy(anchor)
    best = max(records, key=_quality)

    base["record_stage"] = "CANONICALIZED"
    base["canonical_id"] = _canonical_id(anchor)

    if _quality(best) > _quality(base):
        base["description"] = copy.deepcopy(best.get("description") or base.get("description") or {})

    for record in sorted(records, key=_quality, reverse=True):
        _fill_missing(
            base.setdefault("position", {}), record.get("position") or {},
            ("title_normalized", "institution_raw", "institution_normalized", "department", "role_family", "role_level", "employment_type", "workplace_mode"),
        )
        _fill_missing(base.setdefault("location", {}), record.get("location") or {}, ("country_code", "country_name", "city", "region"))
        _fill_missing(base.setdefault("dates", {}), record.get("dates") or {}, ("posted_at", "deadline_at", "deadline_text", "deadline_status", "collected_at"))
        _fill_missing(base.setdefault("contract", {}), record.get("contract") or {}, ("term_type", "duration_months", "fte"))
        _fill_missing(base.setdefault("contract", {}).setdefault("salary", {}), (record.get("contract") or {}).get("salary") or {}, ("min", "max", "currency", "period", "raw_text"))

    known_deadlines = sorted({
        str((record.get("dates") or {}).get("deadline_at"))
        for record in records if (record.get("dates") or {}).get("deadline_at")
    })
    if known_deadlines:
        base["dates"]["deadline_at"] = known_deadlines[0]
        base["dates"]["deadline_status"] = "KNOWN"

    _merge_requirements(records, base)
    _merge_classification(records, base)

    provenance = base.setdefault("provenance", {})
    observed: list[str] = []
    notes: list[str] = []
    observations: list[dict[str, Any]] = []
    for record in records:
        source = _source(record)
        for item in (record.get("provenance") or {}).get("observed_by_sources") or [source.get("source_key")]:
            if item and item not in observed:
                observed.append(str(item))
        for note in (record.get("provenance") or {}).get("notes") or []:
            if note not in notes:
                notes.append(str(note))
        observations.append({
            "source_key": source.get("source_key"),
            "source_kind": source.get("source_kind"),
            "source_job_id": source.get("source_job_id"),
            "source_status": source.get("source_status"),
            "detail_url": source.get("detail_url"),
            "apply_url": source.get("apply_url"),
            "detail_status": _description(record).get("detail_status"),
        })
    provenance["observed_by_sources"] = observed or [str(_source(anchor).get("source_key") or "unknown")]
    provenance["notes"] = notes + [f"Stage 10 central canonicalization clustered {len(records)} source observation(s)."]

    raw_extra = base.setdefault("raw_extra", {})
    raw_extra["canonicalization"] = {
        "anchor_source_key": _source(anchor).get("source_key"),
        "anchor_source_job_id": _source(anchor).get("source_job_id"),
        "trusted_detail_source_key": _source(best).get("source_key"),
        "source_observations": observations,
        "source_status_conflict": len({str(item.get("source_status") or "UNKNOWN") for item in observations}) > 1,
    }
    return base


def canonicalize_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    clusters: list[list[dict[str, Any]]] = []
    for incoming in records:
        match_index: int | None = None
        for index, cluster in enumerate(clusters):
            if any(_same_vacancy(existing, incoming) for existing in cluster):
                match_index = index
                break
        if match_index is None:
            clusters.append([incoming])
        else:
            clusters[match_index].append(incoming)

    canonical = [_merge_group(cluster) for cluster in clusters]
    cross_source_clusters = 0
    for cluster in clusters:
        source_keys = {str(_source(record).get("source_key") or "") for record in cluster}
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
