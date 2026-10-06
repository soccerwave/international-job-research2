from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable

from src.llm.openai_transport import OpenAIChatCompletionsTransport, OpenAITransportConfig
from src.llm.shadow_evaluator import ShadowEvaluationError, ShadowEvaluator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "llm_candidate_profile_v1.json"


def _iter_jobs(path: Path) -> Iterable[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("JSON input must be a list of canonical jobs")
        for row in payload:
            if not isinstance(row, dict):
                raise ValueError("each canonical job must be an object")
            yield row
        return
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"line {line_no} is not a JSON object")
        yield row


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the independent L2 LLM evaluator in shadow mode.")
    parser.add_argument("--input", required=True, type=Path, help="Canonical jobs JSON array or JSONL file")
    parser.add_argument("--shadow-output", required=True, type=Path, help="Append-only shadow result JSONL")
    parser.add_argument("--telemetry-output", required=True, type=Path, help="Append-only telemetry JSONL")
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=Path(os.environ["LLM_SHADOW_CACHE_PATH"]) if os.getenv("LLM_SHADOW_CACHE_PATH") else None,
        help="Persistent successful-evaluation cache JSONL. Defaults to llm_evaluation_cache.jsonl beside shadow output.",
    )
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--model", default=os.getenv("LLM_SHADOW_MODEL", "gpt-6-luna"))
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required for the OpenAI shadow transport")

    cache_path = args.cache_path or args.shadow_output.with_name("llm_evaluation_cache.jsonl")
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    transport = OpenAIChatCompletionsTransport(
        OpenAITransportConfig(api_key=api_key, model=args.model, base_url=args.base_url)
    )
    evaluator = ShadowEvaluator(
        transport=transport,
        candidate_profile=profile,
        shadow_path=args.shadow_output,
        telemetry_path=args.telemetry_output,
        cache_path=cache_path,
    )

    total = 0
    succeeded = 0
    failed = 0
    cache_hits = 0
    for job in _iter_jobs(args.input):
        total += 1
        try:
            result = evaluator.evaluate(job)
            succeeded += 1
            if result.get("cache_hit") is True:
                cache_hits += 1
        except ShadowEvaluationError as exc:
            failed += 1
            print(json.dumps({"status": "FAILED", "job": job.get("canonical_id") or job.get("source_record_id"), "error": str(exc)}, ensure_ascii=False))

    print(json.dumps({
        "status": "COMPLETE" if failed == 0 else "COMPLETE_WITH_ERRORS",
        "model": args.model,
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "cache_hits": cache_hits,
        "api_evaluations": succeeded - cache_hits,
        "shadow_output": str(args.shadow_output),
        "telemetry_output": str(args.telemetry_output),
        "cache_path": str(cache_path),
    }, ensure_ascii=False, indent=2))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
