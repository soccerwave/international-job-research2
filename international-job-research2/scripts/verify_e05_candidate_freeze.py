from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST = Path("validation/e05_candidate_freeze.json")


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def main() -> int:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "E05_CANDIDATE_FREEZE_V1.0.0":
        raise SystemExit("unexpected E0.5 freeze schema")

    status = payload.get("status")
    if status not in {"FROZEN_FOR_FRESH_BLIND_VALIDATION", "REJECTED_FRESH_BLIND_VALIDATION"}:
        raise SystemExit(f"unexpected E0.5 candidate status: {status}")
    if payload.get("promotion_status") != "NOT_PROMOTED":
        raise SystemExit("E0.5 lifecycle must not claim promotion")
    if payload.get("holdout_opened") is not False:
        raise SystemExit("final sealed holdout must remain unopened")

    candidate = payload.get("candidate") or {}
    if candidate.get("evaluator_version") != "E0.5_GENERALIZATION_CANDIDATE":
        raise SystemExit("unexpected evaluator version in E0.5 freeze manifest")
    path = Path(str(candidate.get("path") or ""))
    if not path.is_file():
        raise SystemExit(f"frozen evaluator file is missing: {path}")
    actual = git_blob_sha(path.read_bytes())
    expected = str(candidate.get("candidate_blob_sha") or "")
    if actual != expected:
        raise SystemExit(
            "E0.5 candidate freeze violation: evaluator blob changed after freeze; "
            f"expected {expected}, got {actual}. Start a new candidate cycle instead."
        )

    dev = payload.get("development_evidence") or {}
    if dev.get("classification") != "DEVELOPMENT_ONLY_NOT_PROMOTION_EVIDENCE":
        raise SystemExit("E0.5 development evidence is incorrectly classified")
    for key, total in (
        ("burned_e042_blind_set", 42),
        ("burned_e03_validation", 38),
        ("temporal_development", 17),
    ):
        evidence = dev.get(key) or {}
        if evidence.get("classification") != "DEVELOPMENT_ONLY_NOT_PROMOTION_EVIDENCE":
            raise SystemExit(f"{key} must remain development-only evidence")
        if evidence.get("total") != total:
            raise SystemExit(f"unexpected {key} sample count")
        for metric in ("accuracy", "surfaced_precision", "surfaced_recall"):
            if not 0.0 <= float(evidence.get(metric, -1)) <= 1.0:
                raise SystemExit(f"invalid {key} {metric}")

    gate = payload.get("fresh_blind_validation_gate") or {}
    expected_thresholds = {
        "minimum_accuracy": 0.90,
        "minimum_surfaced_precision": 0.90,
        "minimum_surfaced_recall": 0.75,
    }
    for key, expected_value in expected_thresholds.items():
        if float(gate.get(key, -1)) != expected_value:
            raise SystemExit(f"unexpected fresh blind threshold {key}")

    methodology = payload.get("methodology") or {}
    required_true = (
        "false_negative_cost_exceeds_false_positive_cost",
        "ambiguity_is_fail_open",
        "burned_e042_set_is_not_promotion_evidence",
        "burned_e03_set_is_not_promotion_evidence",
        "temporal_development_set_is_not_promotion_evidence",
        "development_exact_match_is_not_sufficient_for_promotion",
        "candidate_must_not_change_after_freeze_without_starting_a_new_candidate_cycle",
        "holdout_must_remain_sealed_until_fresh_blind_gate_passes",
    )
    for key in required_true:
        if methodology.get(key) is not True:
            raise SystemExit(f"E0.5 methodology invariant missing: {key}")

    if status == "FROZEN_FOR_FRESH_BLIND_VALIDATION":
        if gate.get("classification") != "FUTURE_FRESH_POST_FREEZE_PROMOTION_VALIDATION":
            raise SystemExit("pending fresh blind gate classification is missing")
        if gate.get("result") != "PENDING":
            raise SystemExit("fresh blind validation must be pending at candidate freeze")
        print(f"E0.5 candidate freeze PASS: {path} blob={actual}")
        print("Promotion status: NOT_PROMOTED; fresh blind validation pending; holdout sealed.")
        return 0

    if gate.get("classification") != "FRESH_POST_FREEZE_PROMOTION_VALIDATION":
        raise SystemExit("rejected candidate is missing fresh blind validation classification")
    if gate.get("result") != "FAIL" or gate.get("decision") != "REJECT_E0.5_FOR_PROMOTION":
        raise SystemExit("rejected candidate must record failed fresh blind decision")
    if gate.get("selection_count") != 64 or gate.get("correct") != 53:
        raise SystemExit("fresh blind sample counts do not match immutable evidence")
    if float(gate.get("accuracy", -1)) != 0.828125:
        raise SystemExit("fresh blind accuracy does not match immutable evidence")
    if float(gate.get("surfaced_precision", -1)) != 0.5333333333333333:
        raise SystemExit("fresh blind precision does not match immutable evidence")
    if float(gate.get("surfaced_recall", -1)) != 0.7272727272727273:
        raise SystemExit("fresh blind recall does not match immutable evidence")
    if gate.get("critical_false_negative_count") != 3:
        raise SystemExit("fresh blind critical false-negative count does not match immutable evidence")
    if methodology.get("fresh_e05_blind_set_is_now_burned_for_future_candidates") is not True:
        raise SystemExit("failed E0.5 blind set must be burned for future promotion attempts")
    if methodology.get("labels_were_locked_before_predictions") is not True:
        raise SystemExit("label-lock invariant missing")
    for evidence_path in (
        "validation/e05_fresh_blind_labels.json",
        "validation/e05_fresh_blind_result.json",
    ):
        if not Path(evidence_path).is_file():
            raise SystemExit(f"E0.5 lifecycle evidence missing: {evidence_path}")

    print(f"E0.5 candidate lifecycle PASS: status={status} {path} blob={actual}")
    print("Promotion status: NOT_PROMOTED; fresh blind gate failed; holdout remains sealed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
