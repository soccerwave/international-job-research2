from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.canonicalizer import canonicalize_records as legacy_canonicalize
from src.runtime.canonicalizer_fast import canonicalize_records as cached_canonicalize
from src.runtime.finalizer import finalize_run
from src.runtime.preprod import _load_fanin_records


def digest_records(records: list[dict]) -> str:
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run_timed(fn):
    started = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--output-root", default="compare-output")
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    fanin = finalize_run(run_id=args.run_id, artifact_root=artifact_root, output_root=output_root)
    if fanin.status.value != "OK":
        raise RuntimeError(f"Unexpected fanin status: {fanin.status.value}")
    records = _load_fanin_records(run_id=args.run_id, output_root=output_root)

    (legacy_records, legacy_summary), legacy_seconds = run_timed(lambda: legacy_canonicalize(records))
    print(json.dumps({"phase": "legacy", "elapsed_seconds": round(legacy_seconds, 3)}), flush=True)

    (cached_records, cached_summary), cached_seconds = run_timed(lambda: cached_canonicalize(records))
    print(json.dumps({"phase": "cached", "elapsed_seconds": round(cached_seconds, 3)}), flush=True)

    legacy_digest = digest_records(legacy_records)
    cached_digest = digest_records(cached_records)
    equivalent = legacy_summary == cached_summary and legacy_digest == cached_digest
    result = {
        "status": "PASS" if equivalent else "FAIL",
        "run_id": args.run_id,
        "input_records": len(records),
        "legacy_summary": legacy_summary,
        "cached_summary": cached_summary,
        "legacy_digest": legacy_digest,
        "cached_digest": cached_digest,
        "exact_output_equivalent": legacy_digest == cached_digest,
        "summary_equivalent": legacy_summary == cached_summary,
        "legacy_seconds": round(legacy_seconds, 3),
        "cached_seconds": round(cached_seconds, 3),
        "speedup": round(legacy_seconds / cached_seconds, 3) if cached_seconds else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0 if equivalent else 2


if __name__ == "__main__":
    raise SystemExit(main())
