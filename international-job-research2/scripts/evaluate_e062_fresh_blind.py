from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from src.evaluation.calibrated_e062 import EVALUATOR_VERSION, evaluate_calibrated

SURFACED = {"STRONG_APPLY", "APPLY", "REVIEW"}
CANDIDATE_PATH = Path("src/evaluation/calibrated_e062.py")
EXPECTED_LABEL_SCHEMA = "E062_FRESH_BLIND_LABELS_V1.0.0"
EXPECTED_LABEL_STATUS = "LABELS_LOCKED_BEFORE_E062_SCORING"


def _expected(item: dict) -> str:
    return str(item.get("expected_recommendation") or "").upper()


def _float_01(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("threshold must be between 0 and 1")
    return parsed


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description="Score frozen E0.6.2 once on locked fresh blind labels")
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--min-accuracy", type=_float_01, default=0.90)
    p.add_argument("--min-surfaced-precision", type=_float_01, default=0.90)
    p.add_argument("--min-surfaced-recall", type=_float_01, default=0.75)
    args = p.parse_args()

    payload = json.loads(args.labels.read_text(encoding="utf-8"))
    if payload.get("schema_version") != EXPECTED_LABEL_SCHEMA:
        raise SystemExit("unexpected fresh blind label schema")
    if payload.get("status") != EXPECTED_LABEL_STATUS:
        raise SystemExit("fresh blind labels are not locked")
    if payload.get("candidate_version") != EVALUATOR_VERSION:
        raise SystemExit("label candidate version does not match evaluator")
    if (payload.get("labeling_policy") or {}).get("e062_predictions_consulted") is not False:
        raise SystemExit("labeling policy does not certify prediction blindness")

    expected_blob = str(payload.get("candidate_blob_sha") or "")
    actual_blob = _git_blob_sha(CANDIDATE_PATH.read_bytes())
    if actual_blob != expected_blob:
        raise SystemExit(f"candidate blob mismatch: expected {expected_blob}, got {actual_blob}")

    records = json.loads(args.records.read_text(encoding="utf-8"))
    by_id = {str(x.get("canonical_id")): x for x in records if isinstance(x, dict)}
    label_items = payload.get("labels") or []
    labels = {str(x["canonical_id"]): _expected(x) for x in label_items}
    needs_detail = {str(x["canonical_id"]) for x in label_items if bool(x.get("needs_detail_review"))}

    if len(labels) != int(payload.get("selection_count") or 0):
        raise SystemExit("label count does not match locked selection_count")
    if len(labels) != len(label_items):
        raise SystemExit("duplicate canonical IDs in locked labels")
    allowed = {"STRONG_APPLY", "APPLY", "REVIEW", "SKIP"}
    if not labels or any(v not in allowed for v in labels.values()):
        raise SystemExit("fresh blind labels are empty or malformed")
    missing = sorted(set(labels) - set(by_id))
    if missing:
        raise SystemExit(f"missing labeled IDs: {missing}")

    predicted: dict[str, str] = {}
    confusion: Counter[tuple[str, str]] = Counter()
    mismatches: list[dict] = []
    critical_false_negatives: list[dict] = []

    for cid in sorted(labels):
        record = by_id[cid]
        result = evaluate_calibrated(record)
        pred = str(result.get("recommendation") or "UNKNOWN").upper()
        predicted[cid] = pred
        expected = labels[cid]
        confusion[(expected, pred)] += 1
        if pred != expected:
            mismatch = {
                "canonical_id": cid,
                "expected": expected,
                "predicted": pred,
                "title": str((record.get("position") or {}).get("title_raw") or ""),
                "blocker_codes": list(result.get("blocker_codes") or []),
                "review_codes": list(result.get("review_codes") or []),
            }
            mismatches.append(mismatch)
            if expected in SURFACED and pred not in SURFACED:
                critical_false_negatives.append(mismatch)

    expected_surface = {cid for cid, value in labels.items() if value in SURFACED}
    predicted_surface = {cid for cid, value in predicted.items() if value in SURFACED}
    tp = len(expected_surface & predicted_surface)
    accuracy = (len(labels) - len(mismatches)) / len(labels)
    precision = tp / len(predicted_surface) if predicted_surface else (1.0 if not expected_surface else 0.0)
    recall = tp / len(expected_surface) if expected_surface else 1.0
    detail_surface_recall = (
        len(needs_detail & predicted_surface) / len(needs_detail) if needs_detail else 1.0
    )

    failures: list[str] = []
    if accuracy < args.min_accuracy:
        failures.append(f"accuracy {accuracy:.4f} < {args.min_accuracy:.4f}")
    if precision < args.min_surfaced_precision:
        failures.append(f"surfaced_precision {precision:.4f} < {args.min_surfaced_precision:.4f}")
    if recall < args.min_surfaced_recall:
        failures.append(f"surfaced_recall {recall:.4f} < {args.min_surfaced_recall:.4f}")
    if critical_false_negatives:
        failures.append(f"critical_false_negatives {len(critical_false_negatives)} > 0")

    result_status = "PASS" if not failures else "FAIL"
    out = {
        "schema_version": "E062_FRESH_BLIND_SCORE_V1.0.0",
        "status": "FRESH_POST_FREEZE_PROMOTION_VALIDATION",
        "candidate_version": EVALUATOR_VERSION,
        "candidate_blob_sha": actual_blob,
        "source_run_id": payload.get("source_run_id"),
        "source_artifact_id": payload.get("source_artifact_id"),
        "source_artifact_digest": payload.get("source_artifact_digest"),
        "selection_count": len(labels),
        "correct": len(labels) - len(mismatches),
        "accuracy": accuracy,
        "expected_surfaced": len(expected_surface),
        "predicted_surfaced": len(predicted_surface),
        "surfaced_precision": precision,
        "surfaced_recall": recall,
        "critical_false_negative_count": len(critical_false_negatives),
        "needs_detail_review_count": len(needs_detail),
        "needs_detail_review_surfaced_count": len(needs_detail & predicted_surface),
        "needs_detail_review_surface_recall_observational": detail_surface_recall,
        "thresholds": {
            "minimum_accuracy": args.min_accuracy,
            "minimum_surfaced_precision": args.min_surfaced_precision,
            "minimum_surfaced_recall": args.min_surfaced_recall,
            "critical_false_negative_max": 0,
        },
        "confusion": {f"{a}->{b}": n for (a, b), n in sorted(confusion.items())},
        "mismatches": mismatches,
        "critical_false_negatives": critical_false_negatives,
        "gate_failures": failures,
        "result": result_status,
        "decision": "PROMOTION_ELIGIBLE_FOR_FINAL_HOLDOUT" if not failures else "REJECT_E0.6.2_FOR_PROMOTION",
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
