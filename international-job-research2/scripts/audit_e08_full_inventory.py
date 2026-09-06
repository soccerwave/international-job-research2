from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.evaluation.calibrated_e07 import evaluate_calibrated as evaluate_e07
from src.evaluation.calibrated_e08 import evaluate_calibrated as evaluate_e08


def main() -> int:
    p = argparse.ArgumentParser(description="Development-only full-inventory delta audit for E0.8 vs E0.7")
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    records = json.loads(args.records.read_text(encoding="utf-8"))
    route_before = Counter()
    route_after = Counter()
    recommendation_before = Counter()
    recommendation_after = Counter()
    deltas: list[dict] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        before = evaluate_e07(record)
        after = evaluate_e08(record)
        rb = str(before.get("operational_route") or "HIDDEN").upper()
        ra = str(after.get("operational_route") or "HIDDEN").upper()
        pb = str(before.get("recommendation") or "UNKNOWN").upper()
        pa = str(after.get("recommendation") or "UNKNOWN").upper()
        route_before[rb] += 1
        route_after[ra] += 1
        recommendation_before[pb] += 1
        recommendation_after[pa] += 1
        if rb != ra or pb != pa or bool(before.get("needs_detail_review")) != bool(after.get("needs_detail_review")):
            deltas.append({
                "canonical_id": str(record.get("canonical_id") or ""),
                "title": str((record.get("position") or {}).get("title_raw") or ""),
                "route_before": rb,
                "route_after": ra,
                "recommendation_before": pb,
                "recommendation_after": pa,
                "needs_detail_before": bool(before.get("needs_detail_review")),
                "needs_detail_after": bool(after.get("needs_detail_review")),
                "blocker_codes_after": list(after.get("blocker_codes") or []),
                "review_codes_after": list(after.get("review_codes") or []),
                "detail_review_codes_after": list(after.get("detail_review_codes") or []),
            })

    out = {
        "schema_version": "E08_FULL_INVENTORY_DELTA_V1.0.0",
        "status": "DEVELOPMENT_ONLY_NOT_PROMOTION_EVIDENCE",
        "record_count": sum(route_before.values()),
        "route_before": dict(sorted(route_before.items())),
        "route_after": dict(sorted(route_after.items())),
        "recommendation_before": dict(sorted(recommendation_before.items())),
        "recommendation_after": dict(sorted(recommendation_after.items())),
        "changed_record_count": len(deltas),
        "deltas": deltas,
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
