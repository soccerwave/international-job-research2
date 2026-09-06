from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.evaluation.calibrated_e042 import EVALUATOR_VERSION, evaluate_calibrated

ACTIONABLE = {"STRONG_APPLY", "APPLY", "REVIEW"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    records = json.loads(args.records.read_text(encoding="utf-8"))
    by_id = {str(x.get("canonical_id")): x for x in records if isinstance(x, dict)}
    payload = json.loads(args.labels.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "E04_TEMPORAL_DEVELOPMENT_LABELS_V1.0.0":
        raise SystemExit("unexpected E0.4 development label schema")

    labels = {str(x["canonical_id"]): str(x["expected"]).upper() for x in payload["labels"]}
    missing = sorted(set(labels) - set(by_id))
    if missing:
        raise SystemExit(f"missing labeled IDs: {missing}")

    confusion: Counter[tuple[str, str]] = Counter()
    mismatches = []
    predicted = {}
    for cid in sorted(labels):
        result = evaluate_calibrated(by_id[cid])
        pred = str(result.get("recommendation") or "UNKNOWN").upper()
        predicted[cid] = pred
        confusion[(labels[cid], pred)] += 1
        if pred != labels[cid]:
            mismatches.append({
                "canonical_id": cid,
                "expected": labels[cid],
                "predicted": pred,
                "title": str((by_id[cid].get("position") or {}).get("title_raw") or ""),
                "blocker_codes": list(result.get("blocker_codes") or []),
                "review_codes": list(result.get("review_codes") or []),
                "reason": str(result.get("reason") or ""),
            })

    expected_clean = {cid for cid, value in labels.items() if value in ACTIONABLE}
    predicted_clean = {cid for cid, value in predicted.items() if value in ACTIONABLE}
    tp = len(expected_clean & predicted_clean)
    out = {
        "schema_version": "E042_TEMPORAL_DEVELOPMENT_SCORE_V1.0.0",
        "status": "DEVELOPMENT_ONLY_NOT_PROMOTION_EVIDENCE",
        "evaluator_version": EVALUATOR_VERSION,
        "total": len(labels),
        "correct": len(labels) - len(mismatches),
        "accuracy": (len(labels) - len(mismatches)) / len(labels),
        "expected_clean": len(expected_clean),
        "predicted_clean": len(predicted_clean),
        "clean_precision": tp / len(predicted_clean) if predicted_clean else 1.0,
        "clean_recall": tp / len(expected_clean) if expected_clean else 1.0,
        "confusion": {f"{a}->{b}": n for (a, b), n in sorted(confusion.items())},
        "mismatches": mismatches,
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
