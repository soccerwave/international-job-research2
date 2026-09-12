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
from src.runtime.canonicalizer_fast import canonicalize_records as candidate_canonicalize
from src.runtime.finalizer import finalize_run
from src.runtime.preprod import _load_fanin_records


def digest_records(records: list[dict]) -> str:
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--implementation", choices=("legacy", "candidate"), required=True)
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--output-root", default="compare-output")
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    fanin = finalize_run(run_id=args.run_id, artifact_root=artifact_root, output_root=output_root)
    if fanin.status.value != "OK":
        raise RuntimeError(f"Unexpected fanin status: {fanin.status.value}")
    records = _load_fanin_records(run_id=args.run_id, output_root=output_root)

    implementation = legacy_canonicalize if args.implementation == "legacy" else candidate_canonicalize
    started = time.perf_counter()
    canonical_records, summary = implementation(records)
    elapsed_seconds = time.perf_counter() - started

    result = {
        "implementation": args.implementation,
        "run_id": args.run_id,
        "input_records": len(records),
        "summary": summary,
        "digest": digest_records(canonical_records),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }
    result_path = Path(args.result_json)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
