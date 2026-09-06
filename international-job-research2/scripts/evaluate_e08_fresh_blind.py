from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from src.evaluation.calibrated_e08 import EVALUATOR_VERSION, evaluate_calibrated

CANDIDATE_PATH = Path("src/evaluation/calibrated_e08.py")
FREEZE_PATH = Path("validation/e08_candidate_freeze.json")
SURFACED_ROUTES = {"JOBS", "NEEDS_DETAIL_REVIEW"}
VALID_ROUTES = {"JOBS", "NEEDS_DETAIL_REVIEW", "HIDDEN"}


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description="Score frozen E0.8 once on locked fresh route labels")
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    if freeze.get("schema_version") != "E08_CANDIDATE_FREEZE_V1.0.0":
        raise SystemExit("unexpected E0.8 freeze schema")
    if freeze.get("status") != "FROZEN_FOR_FRESH_BLIND_VALIDATION":
        raise SystemExit("E0.8 candidate is not frozen for fresh blind validation")
    if freeze.get("promotion_status") != "NOT_PROMOTED" or freeze.get("holdout_opened") is not False:
        raise SystemExit("E0.8 lifecycle state is invalid before fresh blind scoring")
    if freeze.get("stop_policy", {}).get("e08_is_last_candidate_in_current_evaluator_roadmap") is not True:
        raise SystemExit("E0.8 hard stop policy is not locked")

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    if selection.get("schema_version") != "E08_FRESH_BLIND_SELECTION_V1.0.0":
        raise SystemExit("unexpected E0.8 selection schema")
    if selection.get("status") != "SELECTION_LOCKED_BEFORE_E08_SCORING":
        raise SystemExit("E0.8 selection is not locked")

    payload = json.loads(args.labels.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "E08_FRESH_BLIND_LABELS_V1.0.0":
        raise SystemExit("unexpected E0.8 label schema")
    if payload.get("status") != "LABELS_LOCKED_BEFORE_E08_SCORING":
        raise SystemExit("E0.8 labels are not locked")
    if payload.get("candidate_version") != EVALUATOR_VERSION or selection.get("candidate_version") != EVALUATOR_VERSION:
        raise SystemExit("candidate version mismatch")

    actual_blob = _git_blob_sha(CANDIDATE_PATH.read_bytes())
    expected_blob = str(freeze.get("candidate", {}).get("candidate_blob_sha") or "")
    if not expected_blob or actual_blob != expected_blob:
        raise SystemExit(f"candidate blob mismatch vs freeze: expected {expected_blob}, got {actual_blob}")
    if str(payload.get("candidate_blob_sha") or "") != actual_blob or str(selection.get("candidate_blob_sha") or "") != actual_blob:
        raise SystemExit("selection/labels candidate blob does not match frozen evaluator")

    source_tuple = (
        int(selection.get("source_run_id") or 0),
        int(selection.get("source_artifact_id") or 0),
        str(selection.get("source_artifact_digest") or ""),
    )
    label_source_tuple = (
        int(payload.get("source_run_id") or 0),
        int(payload.get("source_artifact_id") or 0),
        str(payload.get("source_artifact_digest") or ""),
    )
    if source_tuple != label_source_tuple:
        raise SystemExit("selection and labels do not reference the same frozen production artifact")

    selected = selection.get("selected") or []
    labels = payload.get("labels") or []
    expected_count = int(selection.get("selection_count") or 0)
    if len(selected) != expected_count or len(labels) != expected_count or int(payload.get("selection_count") or 0) != expected_count:
        raise SystemExit("selection/label count mismatch")

    selected_ids = [str(x.get("canonical_id") or "") for x in selected]
    label_ids = [str(x.get("canonical_id") or "") for x in labels]
    if len(set(selected_ids)) != len(selected_ids) or len(set(label_ids)) != len(label_ids):
        raise SystemExit("duplicate canonical IDs in selection or labels")
    if set(selected_ids) != set(label_ids):
        raise SystemExit("locked selection IDs and locked label IDs differ")

    records = json.loads(args.records.read_text(encoding="utf-8"))
    by_id = {str(r.get("canonical_id")): r for r in records if isinstance(r, dict)}
    missing = sorted(set(selected_ids) - set(by_id))
    if missing:
        raise SystemExit(f"selected records missing from source inventory: {missing}")

    confusion: Counter[tuple[str, str]] = Counter()
    mismatches: list[dict] = []
    critical_false_negatives: list[dict] = []
    detail_review_false_negatives: list[dict] = []
    expected_surface: set[str] = set()
    predicted_surface: set[str] = set()
    expected_detail: set[str] = set()
    predicted_detail: set[str] = set()
    jobs_recommendation_checks: list[dict] = []

    for item in labels:
        cid = str(item.get("canonical_id") or "")
        expected = str(item.get("expected_route") or "").upper()
        if expected not in VALID_ROUTES:
            raise SystemExit(f"invalid route label: {cid} -> {expected}")

        result = evaluate_calibrated(by_id[cid])
        predicted = str(result.get("operational_route") or "HIDDEN").upper()
        if predicted not in VALID_ROUTES:
            predicted = "HIDDEN"
        confusion[(expected, predicted)] += 1

        if expected in SURFACED_ROUTES:
            expected_surface.add(cid)
        if predicted in SURFACED_ROUTES:
            predicted_surface.add(cid)
        if expected == "NEEDS_DETAIL_REVIEW":
            expected_detail.add(cid)
        if predicted == "NEEDS_DETAIL_REVIEW":
            predicted_detail.add(cid)

        title = str((by_id[cid].get("position") or {}).get("title_raw") or "")
        if predicted != expected:
            row = {
                "canonical_id": cid,
                "title": title,
                "expected_route": expected,
                "predicted_route": predicted,
                "predicted_recommendation": str(result.get("recommendation") or "UNKNOWN").upper(),
                "needs_detail_review": bool(result.get("needs_detail_review")),
                "blocker_codes": list(result.get("blocker_codes") or []),
                "review_codes": list(result.get("review_codes") or []),
                "detail_review_codes": list(result.get("detail_review_codes") or []),
            }
            mismatches.append(row)
            if expected in SURFACED_ROUTES and predicted == "HIDDEN":
                critical_false_negatives.append(row)
            if expected == "NEEDS_DETAIL_REVIEW" and predicted != "NEEDS_DETAIL_REVIEW":
                detail_review_false_negatives.append(row)

        expected_rec = item.get("expected_recommendation")
        if expected == "JOBS" and expected_rec:
            jobs_recommendation_checks.append({
                "canonical_id": cid,
                "title": title,
                "expected_recommendation": str(expected_rec).upper(),
                "predicted_recommendation": str(result.get("recommendation") or "UNKNOWN").upper(),
            })

    total = len(labels)
    correct = total - len(mismatches)
    route_accuracy = correct / total if total else 0.0
    tp = len(expected_surface & predicted_surface)
    surfaced_precision = tp / len(predicted_surface) if predicted_surface else (1.0 if not expected_surface else 0.0)
    surfaced_recall = tp / len(expected_surface) if expected_surface else 1.0
    detail_recall = len(expected_detail & predicted_detail) / len(expected_detail) if expected_detail else 1.0

    thresholds = payload.get("thresholds") or {}
    min_acc = float(thresholds.get("minimum_route_accuracy", 0.90))
    min_prec = float(thresholds.get("minimum_operational_surfaced_precision", 0.90))
    min_rec = float(thresholds.get("minimum_operational_surfaced_recall", 0.75))
    max_critical = int(thresholds.get("critical_operational_false_negative_max", 0))
    max_detail_fn = int(thresholds.get("detail_review_false_negative_max", 0))

    failures: list[str] = []
    if route_accuracy < min_acc:
        failures.append(f"route_accuracy {route_accuracy:.4f} < {min_acc:.4f}")
    if surfaced_precision < min_prec:
        failures.append(f"operational_surfaced_precision {surfaced_precision:.4f} < {min_prec:.4f}")
    if surfaced_recall < min_rec:
        failures.append(f"operational_surfaced_recall {surfaced_recall:.4f} < {min_rec:.4f}")
    if len(critical_false_negatives) > max_critical:
        failures.append(f"critical_operational_false_negatives {len(critical_false_negatives)} > {max_critical}")
    if len(detail_review_false_negatives) > max_detail_fn:
        failures.append(f"detail_review_false_negatives {len(detail_review_false_negatives)} > {max_detail_fn}")

    out = {
        "schema_version": "E08_FRESH_BLIND_SCORE_V1.0.0",
        "status": "FINAL_FRESH_POST_FREEZE_ROUTE_VALIDATION_FOR_ROADMAP",
        "candidate_version": EVALUATOR_VERSION,
        "candidate_blob_sha": actual_blob,
        "freeze_merge_commit": freeze.get("candidate", {}).get("candidate_code_commit"),
        "source_run_id": payload.get("source_run_id"),
        "source_artifact_id": payload.get("source_artifact_id"),
        "source_artifact_digest": payload.get("source_artifact_digest"),
        "selection_count": total,
        "correct_routes": correct,
        "route_accuracy": route_accuracy,
        "expected_operational_surface": len(expected_surface),
        "predicted_operational_surface": len(predicted_surface),
        "operational_surfaced_precision": surfaced_precision,
        "operational_surfaced_recall": surfaced_recall,
        "expected_detail_review": len(expected_detail),
        "predicted_detail_review": len(predicted_detail),
        "detail_review_recall": detail_recall,
        "critical_operational_false_negative_count": len(critical_false_negatives),
        "detail_review_false_negative_count": len(detail_review_false_negatives),
        "thresholds": thresholds,
        "confusion": {f"{a}->{b}": n for (a, b), n in sorted(confusion.items())},
        "mismatches": mismatches,
        "critical_operational_false_negatives": critical_false_negatives,
        "detail_review_false_negatives": detail_review_false_negatives,
        "jobs_recommendation_checks": jobs_recommendation_checks,
        "gate_failures": failures,
        "result": "PASS" if not failures else "FAIL",
        "decision": "ELIGIBLE_FOR_FINAL_SEALED_HOLDOUT" if not failures else "CLOSE_ROADMAP_NO_E0.9",
        "stop_policy_enforced": True,
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
