from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "LLM_EVALUATOR_FREEZE_L1.1.json"


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
        raise SystemExit("LLM_EVALUATOR_FREEZE_L1.1.json is missing")

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if freeze.get("stage") != "L1_CANDIDATE_PROFILE_REPRESENTATION":
        raise SystemExit(f"Unexpected L1 stage: {freeze.get('stage')}")
    if freeze.get("status") != "ACCEPTED":
        raise SystemExit(f"L1 freeze is not accepted: {freeze.get('status')}")
    if freeze.get("profile_version") != "LLM_CANDIDATE_PROFILE_V1.1.0":
        raise SystemExit(f"Unexpected L1 profile version: {freeze.get('profile_version')}")

    protected = freeze.get("protected_git_blobs") or {}
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
        raise SystemExit("L1 candidate profile freeze verification failed:\n" + "\n".join(failures))

    print(json.dumps({
        "status": "PASS",
        "stage": freeze["stage"],
        "profile_version": freeze["profile_version"],
        "protected_file_count": len(protected),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
