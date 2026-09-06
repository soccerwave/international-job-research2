from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST = Path("validation/e062_candidate_freeze.json")


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def main() -> int:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "E062_CANDIDATE_FREEZE_V1.0.0":
        raise SystemExit("unexpected E0.6.2 freeze schema")
    if payload.get("status") != "FROZEN_FOR_FRESH_BLIND_VALIDATION":
        raise SystemExit(f"unexpected E0.6.2 status: {payload.get('status')}")
    if payload.get("promotion_status") != "NOT_PROMOTED":
        raise SystemExit("E0.6.2 freeze must not claim promotion")
    if payload.get("holdout_opened") is not False:
        raise SystemExit("final holdout must remain sealed")

    candidate = payload.get("candidate") or {}
    if candidate.get("evaluator_version") != "E0.6.2_CONTEXT_LOCALIZATION_CANDIDATE":
        raise SystemExit("unexpected E0.6.2 evaluator version")
    path = Path(str(candidate.get("path") or ""))
    if not path.is_file():
        raise SystemExit(f"frozen candidate is missing: {path}")
    actual = git_blob_sha(path.read_bytes())
    expected = str(candidate.get("candidate_blob_sha") or "")
    if actual != expected:
        raise SystemExit(
            "E0.6.2 candidate freeze violation: evaluator blob changed after freeze; "
            f"expected {expected}, got {actual}. Start a new candidate cycle."
        )

    dev = payload.get("development_evidence") or {}
    if dev.get("classification") != "DEVELOPMENT_ONLY_NOT_PROMOTION_EVIDENCE":
        raise SystemExit("E0.6.2 development evidence is incorrectly classified")
    expected_sets = {
        "burned_e05_fresh_blind": 64,
        "burned_e042_blind": 42,
        "burned_e03_validation": 38,
        "temporal_development": 17,
    }
    for key, total in expected_sets.items():
        evidence = dev.get(key) or {}
        if evidence.get("classification") != "DEVELOPMENT_ONLY_NOT_PROMOTION_EVIDENCE":
            raise SystemExit(f"{key} must remain development-only evidence")
        if evidence.get("total") != total or evidence.get("correct") != total:
            raise SystemExit(f"unexpected {key} exact-match evidence")
        if float(evidence.get("accuracy", -1)) != 1.0:
            raise SystemExit(f"unexpected {key} accuracy")
        if float(evidence.get("surfaced_precision", -1)) != 1.0:
            raise SystemExit(f"unexpected {key} surfaced precision")
        if float(evidence.get("surfaced_recall", -1)) != 1.0:
            raise SystemExit(f"unexpected {key} surfaced recall")
        if int(evidence.get("critical_false_negative_count", -1)) != 0:
            raise SystemExit(f"unexpected {key} critical false negatives")

    gates = payload.get("fresh_blind_validation_gate") or {}
    if gates.get("classification") != "FUTURE_FRESH_POST_FREEZE_PROMOTION_VALIDATION":
        raise SystemExit("fresh blind gate classification is missing")
    if gates.get("result") != "PENDING":
        raise SystemExit("fresh blind validation must remain pending at freeze")
    expected_thresholds = {
        "minimum_accuracy": 0.90,
        "minimum_surfaced_precision": 0.90,
        "minimum_surfaced_recall": 0.75,
        "critical_false_negative_max": 0,
    }
    for key, expected_value in expected_thresholds.items():
        if gates.get(key) != expected_value:
            raise SystemExit(f"unexpected fresh blind threshold {key}")

    methodology = payload.get("methodology") or {}
    required_true = (
        "false_negative_cost_exceeds_false_positive_cost",
        "ambiguity_is_fail_open",
        "burned_e05_set_is_not_promotion_evidence",
        "burned_e042_set_is_not_promotion_evidence",
        "burned_e03_set_is_not_promotion_evidence",
        "temporal_development_set_is_not_promotion_evidence",
        "development_exact_match_is_not_sufficient_for_promotion",
        "candidate_must_not_change_after_freeze_without_starting_a_new_candidate_cycle",
        "holdout_must_remain_sealed_until_fresh_blind_gate_passes",
    )
    for key in required_true:
        if methodology.get(key) is not True:
            raise SystemExit(f"methodology invariant missing: {key}")

    print(f"E0.6.2 candidate freeze PASS: {path} blob={actual}")
    print("Promotion status: NOT_PROMOTED; fresh post-freeze blind validation required; holdout sealed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
