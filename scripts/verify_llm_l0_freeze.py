from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "LLM_EVALUATOR_FREEZE_L0.1.json"


def git_blob_sha(path: Path) -> str:
    result = subprocess.run(
        ["git", "hash-object", str(path.relative_to(ROOT))],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    if not FREEZE.exists():
        raise SystemExit("LLM_EVALUATOR_FREEZE_L0.1.json is missing")

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if freeze.get("llm_contract_version") != "LLM_EVALUATOR_CONTRACT_V0.1":
        raise SystemExit(f"Unexpected LLM contract version: {freeze.get('llm_contract_version')}")
    if freeze.get("pipeline_stage") != "L0_LLM_CONTRACT_DESIGN_FREEZE":
        raise SystemExit(f"Unexpected LLM pipeline stage: {freeze.get('pipeline_stage')}")
    if freeze.get("status") != "ACCEPTED":
        raise SystemExit(f"Unexpected L0 status: {freeze.get('status')}")

    protected = freeze.get("protected_git_blobs") or {}
    if not protected:
        raise SystemExit("L0 freeze manifest has no protected_git_blobs")

    failures: list[str] = []
    for rel, expected in sorted(protected.items()):
        path = ROOT / rel
        if not path.exists():
            failures.append(f"missing: {rel}")
            continue
        actual = git_blob_sha(path)
        if actual != expected:
            failures.append(f"hash mismatch: {rel}: expected {expected}, got {actual}")

    if failures:
        raise SystemExit("L0 LLM freeze verification failed:\n" + "\n".join(failures))

    print(json.dumps({
        "status": "PASS",
        "llm_contract_version": freeze["llm_contract_version"],
        "pipeline_stage": freeze["pipeline_stage"],
        "protected_file_count": len(protected),
        "next_stage": freeze.get("next_stage"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
