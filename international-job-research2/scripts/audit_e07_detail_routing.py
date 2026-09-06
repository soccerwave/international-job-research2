from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation.calibrated_e062 import evaluate_calibrated as evaluate_e062
from src.evaluation.calibrated_e07 import evaluate_calibrated as evaluate_e07


def main() -> int:
    p = argparse.ArgumentParser(description="Audit E0.7 detail-routing channel on burned E0.6.2 inventory")
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    records = json.loads(args.records.read_text(encoding="utf-8"))
    by_id = {str(r.get("canonical_id")): r for r in records if isinstance(r, dict)}

    # E0.7 must not silently retune the E0.6.2 scientific recommendation layer.
    changed_recommendations = []
    detail_ids = []
    for cid, record in by_id.items():
        old = str(evaluate_e062(record).get("recommendation") or "UNKNOWN").upper()
        new_result = evaluate_e07(record)
        new = str(new_result.get("recommendation") or "UNKNOWN").upper()
        if old != new:
            changed_recommendations.append({"canonical_id": cid, "e062": old, "e07": new})
        if bool(new_result.get("needs_detail_review")):
            detail_ids.append(cid)

    required_detail = {
        "vac_3b8885956181e441293e",  # postdoc wrapper; essential requirements in external PDF
        "vac_58beb014b191ec38966f",  # research fellow wrapper; essential requirements external
    }
    required_not_detail = {
        "vac_1dc2a1a8fd8ee1ce13bf",  # fetch-failed but explicit PhD listing
        "vac_84d03f91ef4da34a8bed",   # partial but explicit student role
    }

    missing_required = sorted(required_detail - set(detail_ids))
    polluted_required = sorted(required_not_detail & set(detail_ids))
    failures = []
    if changed_recommendations:
        failures.append(f"scientific recommendation changed for {len(changed_recommendations)} records")
    if missing_required:
        failures.append(f"known unresolved-essential wrappers not routed: {missing_required}")
    if polluted_required:
        failures.append(f"known hard-role skips polluted detail queue: {polluted_required}")

    out = {
        "schema_version": "E07_DETAIL_ROUTING_AUDIT_V1.0.0",
        "records": len(by_id),
        "recommendation_changes_vs_e062": changed_recommendations,
        "needs_detail_review_count": len(detail_ids),
        "needs_detail_review_ids": sorted(detail_ids),
        "required_detail_missing": missing_required,
        "hard_skip_detail_pollution": polluted_required,
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
