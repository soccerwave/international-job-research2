from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST = Path("validation/e042_candidate_freeze.json")


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def main() -> int:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "E042_CANDIDATE_FREEZE_V1.0.0":
        raise SystemExit("unexpected E0.4.2 freeze schema")

    status = payload.get("status")
    if status not in {"FROZEN_FOR_BLIND_VALIDATION", "REJECTED_BLIND_VALIDATION"}:
        raise SystemExit(f"unexpected E0.4.2 candidate lifecycle status: {status}")
    if payload.get("promotion_status") != "NOT_PROMOTED":
        raise SystemExit("freeze verifier must not claim promotion")
    if payload.get("holdout_opened") is not False:
        raise SystemExit("holdout must remain sealed for the E0.4.2 candidate lifecycle")

    candidate = payload.get("candidate") or {}
    if candidate.get("evaluator_version") != "E0.4.2_EVIDENCE_GATED_CANDIDATE":
        raise SystemExit("unexpected evaluator version in freeze manifest")
    path = Path(str(candidate.get("path") or ""))
    if not path.is_file():
        raise SystemExit(f"frozen evaluator file is missing: {path}")

    actual = git_blob_sha(path.read_bytes())
    expected = str(candidate.get("candidate_blob_sha") or "")
    if actual != expected:
        raise SystemExit(
            "E0.4.2 candidate freeze violation: evaluator blob changed after freeze; "
            f"expected {expected}, got {actual}. Start a new candidate cycle instead of mutating the frozen candidate."
        )

    dev = payload.get("development_evidence") or {}
    for key in ("burned_e03_validation", "temporal_development"):
        evidence = dev.get(key) or {}
        if evidence.get("classification") != "DEVELOPMENT_ONLY_NOT_PROMOTION_EVIDENCE":
            raise SystemExit(f"{key} is incorrectly classified as promotion evidence")
        if evidence.get("accuracy") != 1.0 or evidence.get("clean_precision") != 1.0 or evidence.get("clean_recall") != 1.0:
            raise SystemExit(f"{key} freeze metrics do not match the accepted development evidence")
        if evidence.get("mismatches") != 0:
            raise SystemExit(f"{key} contains development mismatches")

    methodology = payload.get("methodology") or {}
    if methodology.get("candidate_must_not_change_after_freeze_without_starting_a_new_candidate_cycle") is not True:
        raise SystemExit("freeze mutation policy missing")

    if status == "REJECTED_BLIND_VALIDATION":
        evidence = payload.get("blind_validation_evidence") or {}
        if evidence.get("classification") != "FRESH_POST_FREEZE_PROMOTION_VALIDATION":
            raise SystemExit("rejected candidate is missing fresh blind validation classification")
        if evidence.get("result") != "FAIL" or evidence.get("decision") != "REJECT_E0.4.2_FOR_PROMOTION":
            raise SystemExit("rejected candidate must record a failed promotion decision")
        if evidence.get("selection_count") != 42 or evidence.get("correct") != 31:
            raise SystemExit("rejected candidate blind-validation counts do not match recorded evidence")
        if methodology.get("fresh_blind_set_is_now_burned_for_future_candidates") is not True:
            raise SystemExit("rejected blind set must be marked burned for future candidates")
        for evidence_path in (
            "validation/e042_blind_production_labels.json",
            "validation/e042_blind_validation_gate.json",
            "validation/e042_blind_validation_result.json",
        ):
            if not Path(evidence_path).is_file():
                raise SystemExit(f"rejected lifecycle evidence is missing: {evidence_path}")

    print(f"E0.4.2 candidate lifecycle PASS: status={status} {path} blob={actual}")
    print("Promotion status: NOT_PROMOTED; holdout remains sealed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
