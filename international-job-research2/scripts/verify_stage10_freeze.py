from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "PREPROD_FREEZE_V1.0.0.json"


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
        raise SystemExit("PREPROD_FREEZE_V1.0.0.json is missing")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if freeze.get("preprod_contract_version") != "PREPROD_RC1_CONTRACT_V1.0.0":
        raise SystemExit(f"Unexpected preprod contract version: {freeze.get('preprod_contract_version')}")
    if freeze.get("pipeline_stage") != "V0.10_PREPROD_RC1":
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
        raise SystemExit("Stage 10 preprod freeze verification failed:\n" + "\n".join(failures))
    print(json.dumps({
        "status": "PASS",
        "preprod_contract_version": freeze["preprod_contract_version"],
        "pipeline_stage": freeze["pipeline_stage"],
        "freeze_status": freeze.get("status"),
        "protected_file_count": len(protected),
        "strict_acceptance_run_id": freeze.get("strict_acceptance_run_id"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
