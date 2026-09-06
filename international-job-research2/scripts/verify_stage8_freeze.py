from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "STATE_FREEZE_V1.0.0.json"


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
        raise SystemExit("STATE_FREEZE_V1.0.0.json is missing")

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if freeze.get("state_semantics_version") != "STATE_SCHEMA_V1.0.0":
        raise SystemExit(f"Unexpected state semantics version: {freeze.get('state_semantics_version')}")
    if freeze.get("pipeline_stage") != "V0.8_STATE_PERSISTENCE":
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
        raise SystemExit("Stage 8 state freeze verification failed:\n" + "\n".join(failures))

    print(json.dumps({
        "status": "PASS",
        "state_semantics_version": freeze["state_semantics_version"],
        "pipeline_stage": freeze["pipeline_stage"],
        "protected_file_count": len(protected),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
