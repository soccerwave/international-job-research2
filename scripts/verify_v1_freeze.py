from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "RELEASE_FREEZE_V1.1.0.json"
PATCH = ROOT / "RELEASE_FREEZE_V1.1.1.json"
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


def protected_blobs(freeze: dict) -> tuple[dict[str, str], str]:
    protected = dict(freeze.get("protected_git_blobs") or {})
    effective_status = str(freeze.get("status") or "")
    if FREEZE.name != "RELEASE_FREEZE_V1.1.0.json" or not PATCH.exists():
        return protected, effective_status

    patch = json.loads(PATCH.read_text(encoding="utf-8"))
    if patch.get("freeze_patch_version") != "V1.1.1":
        raise SystemExit(f"Unexpected V1 freeze patch version: {patch.get('freeze_patch_version')}")
    if patch.get("base_manifest") != FREEZE.name:
        raise SystemExit(f"V1 freeze patch base mismatch: {patch.get('base_manifest')}")

    retired = patch.get("retired_protected_paths") or []
    overrides = patch.get("protected_git_blob_overrides") or {}
    if len(retired) != len(set(retired)):
        raise SystemExit("V1 freeze patch contains duplicate retired paths")
    unknown_retired = sorted(set(retired) - set(protected))
    if unknown_retired:
        raise SystemExit("V1 freeze patch retires unknown protected paths: " + ", ".join(unknown_retired))
    unknown_overrides = sorted(set(overrides) - set(protected))
    if unknown_overrides:
        raise SystemExit("V1 freeze patch overrides unknown protected paths: " + ", ".join(unknown_overrides))
    overlap = sorted(set(retired) & set(overrides))
    if overlap:
        raise SystemExit("V1 freeze patch both retires and overrides: " + ", ".join(overlap))

    for rel in retired:
        protected.pop(rel)
    protected.update(overrides)
    effective_status = str(patch.get("status") or effective_status)
    return protected, effective_status


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

    protected, effective_status = protected_blobs(freeze)
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
        "freeze_status": effective_status,
        "base_manifest": FREEZE.name,
        "freeze_patch": PATCH.name if PATCH.exists() and FREEZE.name == "RELEASE_FREEZE_V1.1.0.json" else None,
        "protected_file_count": len(protected),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
