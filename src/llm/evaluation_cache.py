from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CACHE_FINGERPRINT_VERSION = "LLM_EVALUATION_CACHE_V0.1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def build_cache_fingerprint(
    *,
    llm_input: dict[str, Any],
    candidate_profile: dict[str, Any],
    system_prompt: str,
    output_schema: dict[str, Any],
    transport_identity: str,
) -> str:
    """Return a versioned fingerprint for one semantic LLM evaluation.

    The key intentionally binds the vacancy input, complete candidate profile,
    evaluator prompt/schema and model/provider identity. Reuse is therefore safe
    only when the effective semantic evaluation request is unchanged.
    """

    material = {
        "cache_fingerprint_version": CACHE_FINGERPRINT_VERSION,
        "llm_input": llm_input,
        "candidate_profile": candidate_profile,
        "system_prompt": system_prompt,
        "output_schema": output_schema,
        "transport_identity": transport_identity,
    }
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


def load_successful_cache(path: Path | None) -> dict[str, dict[str, Any]]:
    """Load successful cached shadow records indexed by cache fingerprint.

    Invalid/truncated lines are ignored so an interrupted append cannot make the
    next run unusable. Only records with both a cache fingerprint and llm_result
    are cacheable; failures are never written as successful cache entries.
    """

    if path is None or not path.exists():
        return {}

    out: dict[str, dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        fingerprint = str(row.get("cache_fingerprint") or "").strip()
        if not fingerprint or not isinstance(row.get("llm_result"), dict):
            continue
        out[fingerprint] = row
    return out


def append_cache_record(path: Path | None, row: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_canonical_json(row) + "\n")
