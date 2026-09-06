from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "RELEASE_FREEZE_V1.1.0.json"
if not FREEZE.exists():
    FREEZE = ROOT / "RELEASE_FREEZE_V1.0.0.json"


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
        raise SystemExit("RELEASE_FREEZE_V1.0.0.json is missing")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if freeze.get("production_contract_version") != "PRODUCTION_RUNTIME_V1.0.0":
        raise SystemExit(f"Unexpected production contract: {freeze.get('production_contract_version')}")
    expected_pipeline = ("V1.1_PAGINATED_DISCOVERY" if FREEZE.name == "RELEASE_FREEZE_V1.1.0.json"
                         else "V1.0_VALIDATED_OPERATIONAL_INTERNATIONAL_PIPELINE")
    if freeze.get("pipeline_version") != expected_pipeline:
        raise SystemExit(f"Unexpected pipeline version: {freeze.get('pipeline_version')}")
    protected = freeze.get("protected_git_blobs") or {}
    if not protected:
        raise SystemExit("V1 freeze manifest has no protected_git_blobs")
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
        raise SystemExit("V1 release freeze verification failed:\n" + "\n".join(failures))
    print(json.dumps({
        "status": "PASS",
        "pipeline_version": freeze["pipeline_version"],
        "production_contract_version": freeze["production_contract_version"],
        "freeze_status": freeze.get("status"),
        "protected_file_count": len(protected),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
