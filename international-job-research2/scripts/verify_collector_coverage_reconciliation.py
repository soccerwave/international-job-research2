from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION = ROOT / "validation" / "collector_coverage_reconciliation_2026-09-06.json"

ALLOWED_STATUSES = {
    "IMPLEMENTED_CERTIFIED",
    "IMPLEMENTED_NOT_CERTIFIED",
    "REDUNDANT_VALIDATED",
    "DEFERRED_WITH_REASON",
    "MISSING_ACTION_REQUIRED",
}

EXPECTED_COMMITMENT_IDS = {
    "shared_euraxess_europe",
    "shared_linkedin_europe",
    "shared_linkedin_australia",
    "shared_academicpositions",
    "shared_jobs_ac_uk",
    "thematic_ecss",
    "thematic_dvs",
    "thematic_fens",
    "nl_academictransfer",
    "nl_direct_institutional_backstops",
    "de_academics_de",
    "de_direct_dshs_cologne",
    "de_direct_ruhr_bochum",
    "de_direct_charite",
    "ie_university_vacancies",
    "ie_corehr",
    "uk_direct_institutional_backstops",
    "be_successfactors",
    "be_direct_ku_leuven",
    "be_direct_university_antwerp",
    "fr_cnrs",
    "fr_abg",
    "au_uniroles",
    "au_pageup",
    "au_smartrecruiters",
    "au_workday",
    "at_innsbruck",
    "at_vienna",
}


def verify() -> None:
    data = json.loads(RECONCILIATION.read_text(encoding="utf-8"))

    if data.get("status") != "RECONCILED":
        raise AssertionError("Reconciliation status must be RECONCILED")

    allowed = set(data.get("allowed_statuses") or [])
    if allowed != ALLOWED_STATUSES:
        raise AssertionError(f"Allowed-status contract mismatch: {sorted(allowed)}")

    commitments = data.get("commitments") or []
    ids = [str(item.get("id") or "") for item in commitments]
    if len(ids) != len(set(ids)):
        raise AssertionError("Duplicate reconciliation commitment id")

    actual_ids = set(ids)
    if actual_ids != EXPECTED_COMMITMENT_IDS:
        missing = sorted(EXPECTED_COMMITMENT_IDS - actual_ids)
        unexpected = sorted(actual_ids - EXPECTED_COMMITMENT_IDS)
        raise AssertionError(f"Stage 1 commitment accounting mismatch; missing={missing}, unexpected={unexpected}")

    counts: Counter[str] = Counter()
    for item in commitments:
        status = str(item.get("status") or "")
        if status not in ALLOWED_STATUSES:
            raise AssertionError(f"Invalid status for {item.get('id')}: {status}")
        counts[status] += 1

        if not str(item.get("stage1_commitment") or "").strip():
            raise AssertionError(f"Missing Stage 1 commitment text for {item.get('id')}")
        if not str(item.get("reason") or "").strip():
            raise AssertionError(f"Missing reconciliation reason for {item.get('id')}")
        if not str(item.get("required_action") or "").strip():
            raise AssertionError(f"Missing required action for {item.get('id')}")

        if status == "REDUNDANT_VALIDATED" and "evidence" not in item:
            raise AssertionError(f"REDUNDANT_VALIDATED requires evidence for {item.get('id')}")

    summary = data.get("summary") or {}
    if int(summary.get("commitments_reconciled", -1)) != len(commitments):
        raise AssertionError("Summary commitment count does not match reconciliation entries")

    for status in sorted(ALLOWED_STATUSES):
        if int(summary.get(status, -1)) != counts[status]:
            raise AssertionError(
                f"Summary count mismatch for {status}: summary={summary.get(status)}, actual={counts[status]}"
            )

    if counts["IMPLEMENTED_CERTIFIED"] != 0:
        raise AssertionError("Stage 2 must not silently certify collectors")
    if counts["REDUNDANT_VALIDATED"] != 0:
        raise AssertionError("Stage 2 has no measured redundancy evidence yet")

    governance = data.get("governance_rules") or {}
    required_true = {
        "redundant_requires_measured_overlap_or_recall_evidence",
        "missing_action_required_blocks_final_collector_certification_until_resolved",
    }
    for key in required_true:
        if governance.get(key) is not True:
            raise AssertionError(f"Governance rule must remain true: {key}")

    required_false = {
        "runtime_pass_is_certification",
        "stage5_or_stage6_smoke_pass_is_phase1_certification",
        "deferred_without_recorded_reason_is_accepted",
        "new_source_implementation_in_stage2",
    }
    for key in required_false:
        if governance.get(key) is not False:
            raise AssertionError(f"Governance rule must remain false: {key}")

    print(
        "collector coverage reconciliation verified: "
        f"{len(commitments)} commitments; "
        + ", ".join(f"{status}={counts[status]}" for status in sorted(ALLOWED_STATUSES))
    )


if __name__ == "__main__":
    verify()
