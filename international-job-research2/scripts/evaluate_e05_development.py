from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.evaluation.calibrated_e042 import evaluate_calibrated as evaluate_e042
from src.evaluation.calibrated_e05 import EVALUATOR_VERSION, evaluate_calibrated

SURFACED = {"STRONG_APPLY", "APPLY", "REVIEW"}


def _expected(item: dict) -> str:
    return str(item.get("expected_recommendation") or item.get("expected") or "").upper()


def _float_01(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("threshold must be between 0 and 1")
    return parsed


def main() -> int:
    p = argparse.ArgumentParser(description="Score a burned/development set with E0.5")
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--require-perfect", action="store_true")
    p.add_argument("--min-accuracy", type=_float_01)
    p.add_argument("--min-surfaced-precision", type=_float_01)
    p.add_argument("--min-surfaced-recall", type=_float_01)
    args = p.parse_args()

    records = json.loads(args.records.read_text(encoding="utf-8"))
    by_id = {str(x.get("canonical_id")): x for x in records if isinstance(x, dict)}
    payload = json.loads(args.labels.read_text(encoding="utf-8"))
    labels = {str(x["canonical_id"]): _expected(x) for x in payload.get("labels", [])}
    if not labels or any(not v for v in labels.values()):
        raise SystemExit("development labels are empty or malformed")
    missing = sorted(set(labels) - set(by_id))
    if missing:
        raise SystemExit(f"missing labeled IDs: {missing}")

    confusion: Counter[tuple[str, str]] = Counter()
    mismatches: list[dict] = []
    predicted: dict[str, str] = {}
    for cid in sorted(labels):
        record = by_id[cid]
        base = evaluate_e042(record)
        result = evaluate_calibrated(record)
        pred = str(result.get("recommendation") or "UNKNOWN").upper()
        predicted[cid] = pred
        confusion[(labels[cid], pred)] += 1
        if pred != labels[cid]:
            base_dims = base.get("dimensions") if isinstance(base.get("dimensions"), dict) else {}
            mismatches.append({
                "canonical_id": cid,
                "expected": labels[cid],
                "predicted": pred,
                "title": str((record.get("position") or {}).get("title_raw") or ""),
                "base_recommendation": str(base.get("recommendation") or ""),
                "base_role_family": str(base.get("role_family") or (record.get("position") or {}).get("role_family") or ""),
                "base_role_policy_status": str(base.get("role_policy_status") or ""),
                "base_scientific": str(base_dims.get("scientific") or ""),
                "blocker_codes": list(result.get("blocker_codes") or []),
                "review_codes": list(result.get("review_codes") or []),
            })

    expected_surface = {cid for cid, value in labels.items() if value in SURFACED}
    predicted_surface = {cid for cid, value in predicted.items() if value in SURFACED}
    tp = len(expected_surface & predicted_surface)
    total = len(labels)
    accuracy = (total - len(mismatches)) / total
    precision = tp / len(predicted_surface) if predicted_surface else (1.0 if not expected_surface else 0.0)
    recall = tp / len(expected_surface) if expected_surface else 1.0
    out = {
        "schema_version": "E05_DEVELOPMENT_SCORE_V1.1.0",
        "status": "DEVELOPMENT_ONLY_NOT_PROMOTION_VALIDATION",
        "evaluator_version": EVALUATOR_VERSION,
        "source_label_schema": payload.get("schema_version"),
        "total": total,
        "correct": total - len(mismatches),
        "accuracy": accuracy,
        "expected_surfaced": len(expected_surface),
        "predicted_surfaced": len(predicted_surface),
        "surfaced_precision": precision,
        "surfaced_recall": recall,
        "thresholds": {
            "min_accuracy": args.min_accuracy,
            "min_surfaced_precision": args.min_surfaced_precision,
            "min_surfaced_recall": args.min_surfaced_recall,
            "require_perfect": args.require_perfect,
        },
        "confusion": {f"{a}->{b}": n for (a, b), n in sorted(confusion.items())},
        "mismatches": mismatches,
    }

    failures: list[str] = []
    if args.require_perfect and mismatches:
        failures.append(f"perfect-match gate failed: {len(mismatches)} mismatches")
    if args.min_accuracy is not None and accuracy < args.min_accuracy:
        failures.append(f"accuracy {accuracy:.4f} < {args.min_accuracy:.4f}")
    if args.min_surfaced_precision is not None and precision < args.min_surfaced_precision:
        failures.append(f"surfaced_precision {precision:.4f} < {args.min_surfaced_precision:.4f}")
    if args.min_surfaced_recall is not None and recall < args.min_surfaced_recall:
        failures.append(f"surfaced_recall {recall:.4f} < {args.min_surfaced_recall:.4f}")
    out["gate_failures"] = failures

    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
