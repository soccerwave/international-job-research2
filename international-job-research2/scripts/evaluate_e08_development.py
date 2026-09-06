from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.evaluation.calibrated_e08 import EVALUATOR_VERSION, evaluate_calibrated

SURFACED_ROUTES = {"JOBS", "NEEDS_DETAIL_REVIEW"}
VALID_ROUTES = {"JOBS", "NEEDS_DETAIL_REVIEW", "HIDDEN"}


def main() -> int:
    p = argparse.ArgumentParser(description="Development-only E0.8 scoring on burned E0.7 fresh-blind evidence")
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    payload = json.loads(args.labels.read_text(encoding="utf-8"))
    records = json.loads(args.records.read_text(encoding="utf-8"))
    by_id = {str(r.get("canonical_id")): r for r in records if isinstance(r, dict)}
    labels = payload.get("labels") or []

    confusion: Counter[tuple[str, str]] = Counter()
    mismatches: list[dict] = []
    expected_surface: set[str] = set()
    predicted_surface: set[str] = set()
    expected_detail: set[str] = set()
    predicted_detail: set[str] = set()
    critical: list[dict] = []
    detail_fn: list[dict] = []

    for item in labels:
        cid = str(item.get("canonical_id") or "")
        if cid not in by_id:
            raise SystemExit(f"missing record {cid}")
        expected = str(item.get("expected_route") or "").upper()
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

        if expected != predicted:
            row = {
                "canonical_id": cid,
                "title": str((by_id[cid].get("position") or {}).get("title_raw") or ""),
                "expected_route": expected,
                "predicted_route": predicted,
                "predicted_recommendation": str(result.get("recommendation") or "UNKNOWN").upper(),
                "blocker_codes": list(result.get("blocker_codes") or []),
                "detail_review_codes": list(result.get("detail_review_codes") or []),
            }
            mismatches.append(row)
            if expected in SURFACED_ROUTES and predicted == "HIDDEN":
                critical.append(row)
            if expected == "NEEDS_DETAIL_REVIEW" and predicted != "NEEDS_DETAIL_REVIEW":
                detail_fn.append(row)

    total = len(labels)
    tp = len(expected_surface & predicted_surface)
    out = {
        "schema_version": "E08_DEVELOPMENT_SCORE_V1.0.0",
        "status": "DEVELOPMENT_ONLY_BURNED_E07_EVIDENCE",
        "candidate_version": EVALUATOR_VERSION,
        "selection_count": total,
        "correct_routes": total - len(mismatches),
        "route_accuracy": (total - len(mismatches)) / total if total else 0.0,
        "expected_operational_surface": len(expected_surface),
        "predicted_operational_surface": len(predicted_surface),
        "operational_surfaced_precision": tp / len(predicted_surface) if predicted_surface else (1.0 if not expected_surface else 0.0),
        "operational_surfaced_recall": tp / len(expected_surface) if expected_surface else 1.0,
        "expected_detail_review": len(expected_detail),
        "predicted_detail_review": len(predicted_detail),
        "detail_review_recall": len(expected_detail & predicted_detail) / len(expected_detail) if expected_detail else 1.0,
        "critical_operational_false_negative_count": len(critical),
        "detail_review_false_negative_count": len(detail_fn),
        "confusion": {f"{a}->{b}": n for (a, b), n in sorted(confusion.items())},
        "mismatches": mismatches,
        "critical_operational_false_negatives": critical,
        "detail_review_false_negatives": detail_fn,
        "promotion_evidence": False,
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
