from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.evaluation.calibrated_e06 import EVALUATOR_VERSION, evaluate_calibrated

SURFACED = {"STRONG_APPLY", "APPLY", "REVIEW"}


def _expected(item: dict) -> str:
    return str(item.get("expected_recommendation") or item.get("expected") or "").upper()


def _float_01(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("threshold must be between 0 and 1")
    return parsed


def main() -> int:
    p = argparse.ArgumentParser(description="Score burned/development evidence with E0.6")
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--min-accuracy", type=_float_01, default=0.90)
    p.add_argument("--min-surfaced-precision", type=_float_01, default=0.90)
    p.add_argument("--min-surfaced-recall", type=_float_01, default=0.75)
    p.add_argument("--max-critical-fn", type=int, default=0)
    args = p.parse_args()

    records = json.loads(args.records.read_text(encoding="utf-8"))
    by_id = {str(x.get("canonical_id")): x for x in records if isinstance(x, dict)}
    payload = json.loads(args.labels.read_text(encoding="utf-8"))
    labels = {str(x["canonical_id"]): _expected(x) for x in payload.get("labels", [])}
    if not labels or any(v not in {"STRONG_APPLY", "APPLY", "REVIEW", "SKIP"} for v in labels.values()):
        raise SystemExit("development labels are empty or malformed")
    missing = sorted(set(labels) - set(by_id))
    if missing:
        raise SystemExit(f"missing labeled IDs: {missing}")

    predicted: dict[str, str] = {}
    confusion: Counter[tuple[str, str]] = Counter()
    mismatches: list[dict] = []
    critical_fn: list[dict] = []
    for cid in sorted(labels):
        record = by_id[cid]
        result = evaluate_calibrated(record)
        pred = str(result.get("recommendation") or "UNKNOWN").upper()
        exp = labels[cid]
        predicted[cid] = pred
        confusion[(exp, pred)] += 1
        if pred != exp:
            item = {
                "canonical_id": cid,
                "expected": exp,
                "predicted": pred,
                "title": str((record.get("position") or {}).get("title_raw") or ""),
                "blocker_codes": list(result.get("blocker_codes") or []),
                "review_codes": list(result.get("review_codes") or []),
            }
            mismatches.append(item)
            if exp in SURFACED and pred == "SKIP":
                critical_fn.append(item)

    expected_surface = {cid for cid, value in labels.items() if value in SURFACED}
    predicted_surface = {cid for cid, value in predicted.items() if value in SURFACED}
    tp = len(expected_surface & predicted_surface)
    total = len(labels)
    accuracy = (total - len(mismatches)) / total
    precision = tp / len(predicted_surface) if predicted_surface else (1.0 if not expected_surface else 0.0)
    recall = tp / len(expected_surface) if expected_surface else 1.0

    failures: list[str] = []
    if accuracy < args.min_accuracy:
        failures.append(f"accuracy {accuracy:.4f} < {args.min_accuracy:.4f}")
    if precision < args.min_surfaced_precision:
        failures.append(f"surfaced_precision {precision:.4f} < {args.min_surfaced_precision:.4f}")
    if recall < args.min_surfaced_recall:
        failures.append(f"surfaced_recall {recall:.4f} < {args.min_surfaced_recall:.4f}")
    if len(critical_fn) > args.max_critical_fn:
        failures.append(f"critical_false_negatives {len(critical_fn)} > {args.max_critical_fn}")

    out = {
        "schema_version": "E06_DEVELOPMENT_SCORE_V1.0.0",
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
        "critical_false_negative_count": len(critical_fn),
        "thresholds": {
            "minimum_accuracy": args.min_accuracy,
            "minimum_surfaced_precision": args.min_surfaced_precision,
            "minimum_surfaced_recall": args.min_surfaced_recall,
            "critical_false_negative_max": args.max_critical_fn,
        },
        "confusion": {f"{a}->{b}": n for (a, b), n in sorted(confusion.items())},
        "mismatches": mismatches,
        "critical_false_negatives": critical_fn,
        "gate_failures": failures,
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
