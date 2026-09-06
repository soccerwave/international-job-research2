from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "EVALUATOR_FREEZE_E0.1.json"


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
        raise SystemExit("EVALUATOR_FREEZE_E0.1.json is missing")

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if freeze.get("evaluator_version") != "E0.1":
        raise SystemExit(f"Unexpected evaluator version: {freeze.get('evaluator_version')}")
    if freeze.get("pipeline_stage") != "V0.7_EVALUATOR_BASELINE":
        raise SystemExit(f"Unexpected pipeline stage: {freeze.get('pipeline_stage')}")

    protected = freeze.get("protected_git_blobs") or {}
    if not protected:
        raise SystemExit("Freeze manifest has no protected_git_blobs")

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
        raise SystemExit("Stage 7 evaluator freeze verification failed:\n" + "\n".join(failures))

    print(
        json.dumps(
            {
                "status": "PASS",
                "evaluator_version": freeze["evaluator_version"],
                "pipeline_stage": freeze["pipeline_stage"],
                "protected_file_count": len(protected),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
