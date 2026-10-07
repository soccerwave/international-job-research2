from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm.dual_path_routing import route_dual_path_candidates, routing_summary
from src.llm.experiment_evidence import ExperimentEvidenceError, R2ExperimentEvidenceStore, build_experiment_evidence_bundle, serialize_experiment_evidence
from src.llm.full_evaluation_routing import full_evaluation_summary, run_full_evaluations, select_full_review_candidates
from src.llm.openai_transport import OpenAIChatCompletionsTransport, OpenAITransportConfig
from src.llm.production_shadow import select_production_shadow_inputs
from src.llm.r2_evaluation_cache import R2EvaluationCacheStore
from src.llm.rescue_reject_audit import rescue_reject_audit_summary, run_rescue_reject_audit, select_rescue_reject_audit_candidates
from src.llm.rescue_triage import CLEARLY_OUT_OF_SCOPE, PASS_TO_FULL_REVIEW, RescueTriageError, RescueTriageEvaluator
from src.llm.shadow_evaluator import ShadowEvaluator
from src.reporting.llm_shadow_excel import build_llm_shadow_report_rows, build_llm_shadow_xlsx
from src.reporting.user_excel import load_canonical_records

DEFAULT_PROFILE = ROOT / "config" / "llm_candidate_profile_v1.json"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()


def _full_record_row(record: Any) -> dict[str, Any]:
    return {
        "job_id": record.job_id,
        "origin": record.origin,
        "triage_id": record.triage_id,
        "evaluation": record.evaluation,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the live LLM shadow experiment for one successful production run")
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--model", default=os.getenv("LLM_SHADOW_MODEL", "gpt-6-luna"))
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument(
        "--rescue-reject-audit-size",
        type=int,
        default=int(os.getenv("LLM_RESCUE_REJECT_AUDIT_SIZE", "10")),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    api_key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required")

    records = load_canonical_records(args.records)
    prepared = select_production_shadow_inputs(records)
    routing = route_dual_path_candidates(
        prepared.jobs,
        main_job_ids=prepared.main_job_ids,
        rescue_candidate_job_ids=prepared.rescue_candidate_job_ids,
    )

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "main_job_ids.json", list(prepared.main_job_ids))
    _write_json(out / "rescue_candidate_job_ids.json", list(prepared.rescue_candidate_job_ids))
    _write_json(out / "routing_summary.json", routing_summary(routing))

    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    profile_version = str(profile.get("profile_version") or "").strip()
    if not profile_version:
        raise SystemExit("candidate profile has no profile_version")

    transport = OpenAIChatCompletionsTransport(
        OpenAITransportConfig(
            api_key=api_key,
            model=args.model,
            base_url=args.base_url,
        )
    )

    cache_path = out / "llm_evaluation_cache.jsonl"
    durable_cache = R2EvaluationCacheStore.from_env()
    loaded_cache = durable_cache.hydrate(cache_path)

    failures: list[dict[str, Any]] = []
    triage_records: list[dict[str, Any]] = []

    triage_evaluator = RescueTriageEvaluator(
        transport=transport,
        candidate_profile=profile,
        cache_path=cache_path,
    )
    for routed in routing.rescue_triage:
        try:
            triage_records.append(triage_evaluator.evaluate(routed.job))
        except RescueTriageError as exc:
            failures.append(
                {
                    "job_id": routed.job_id,
                    "origin": "RESCUE_TRIAGE",
                    "error": str(exc),
                }
            )

    _write_jsonl(out / "rescue_triage.jsonl", triage_records)

    # Instantiate after triage so the Full evaluator sees successful triage
    # cache entries appended during this run.
    full_evaluator = ShadowEvaluator(
        transport=transport,
        candidate_profile=profile,
        shadow_path=out / "full_shadow.jsonl",
        telemetry_path=out / "full_telemetry.jsonl",
        cache_path=cache_path,
    )
    selection = select_full_review_candidates(
        routing,
        rescue_triage_records=triage_records,
    )
    full_run = run_full_evaluations(selection, evaluator=full_evaluator)
    failures.extend(dict(row) for row in full_run.failures)

    for job_id in routing.missing_main_ids:
        failures.append({"job_id": job_id, "origin": "ROUTING", "error": "MAIN job ID missing from canonical input"})
    for job_id in routing.missing_rescue_ids:
        failures.append({"job_id": job_id, "origin": "ROUTING", "error": "Rescue job ID missing from canonical input"})
    triage_failed_ids = {str(row.get("job_id") or "") for row in failures if row.get("origin") == "RESCUE_TRIAGE"}
    for job_id in selection.rescue_missing_triage_ids:
        if job_id not in triage_failed_ids:
            failures.append({"job_id": job_id, "origin": "RESCUE_TRIAGE", "error": "No triage result available"})

    audit_selection = select_rescue_reject_audit_candidates(
        routing,
        rescue_triage_records=triage_records,
        run_id=args.run_id,
        sample_size=args.rescue_reject_audit_size,
    )
    audit_run = run_rescue_reject_audit(audit_selection, evaluator=full_evaluator)
    failures.extend(dict(row) for row in audit_run.failures)
    audit_rows = [_full_record_row(row) for row in audit_run.records]
    _write_jsonl(out / "rescue_reject_audit.jsonl", audit_rows)

    full_rows = [_full_record_row(row) for row in full_run.records]
    _write_jsonl(out / "full_evaluations.jsonl", full_rows)
    _write_jsonl(out / "failures.jsonl", failures)

    report_rows = build_llm_shadow_report_rows(
        prepared.jobs,
        main_job_ids=prepared.main_job_ids,
        full_evaluation_records=full_run.records,
    )
    disagreement_rows = [dict(row) for row in report_rows.disagreements]
    _write_jsonl(out / "disagreements.jsonl", disagreement_rows)
    build_llm_shadow_xlsx(
        prepared.jobs,
        out / "llm_shadow_report.xlsx",
        main_job_ids=prepared.main_job_ids,
        full_evaluation_records=full_run.records,
    )

    current_sha = _sha256_file(cache_path)
    if current_sha != loaded_cache.sha256:
        cache_sync = durable_cache.sync(cache_path, expected_etag=loaded_cache.etag)
    else:
        cache_sync = {
            "key": loaded_cache.key,
            "sha256": current_sha,
            "bytes": loaded_cache.bytes_loaded,
            "unchanged": True,
        }

    triage_decisions = Counter(
        str((row.get("llm_result") or {}).get("decision") or "UNKNOWN").upper()
        for row in triage_records
    )
    route_stats = routing_summary(routing)
    full_stats = full_evaluation_summary(selection, full_run)
    audit_stats = rescue_reject_audit_summary(audit_selection, audit_run)
    extra_summary = {
        "main_candidates": len(prepared.main_job_ids),
        "rescue_candidates": len(prepared.rescue_candidate_job_ids),
        "triage_completed": len(triage_records),
        "triage_pass_to_full_review": int(triage_decisions.get(PASS_TO_FULL_REVIEW, 0)),
        "triage_clearly_out_of_scope": int(triage_decisions.get(CLEARLY_OUT_OF_SCOPE, 0)),
        "routing_missing_main": len(route_stats["missing_main_ids"]),
        "routing_missing_rescue": len(route_stats["missing_rescue_ids"]),
        "full_selected": int(full_stats["selected_full_review"]),
        "full_completed": int(full_stats["completed"]),
        "full_failed": int(full_stats["failed"]),
        "llm_rescued_visible": len(report_rows.llm_rescued),
        "main_disagreements": len(report_rows.disagreements),
        "rescue_reject_audit_population": int(audit_stats["population_size"]),
        "rescue_reject_audit_selected": int(audit_stats["selected_sample_size"]),
        "rescue_reject_audit_completed": int(audit_stats["completed"]),
        "rescue_reject_audit_favorable_full_reviews": int(audit_stats["favorable_full_reviews"]),
    }

    run_date = datetime.now(timezone.utc).date().isoformat()
    bundle = build_experiment_evidence_bundle(
        run_id=args.run_id,
        run_date=run_date,
        model=args.model,
        candidate_profile_version=profile_version,
        canonical_jobs=prepared.jobs,
        full_evaluation_records=full_run.records,
        rescue_triage_records=triage_records,
        rescue_reject_audit_records=audit_run.records,
        disagreement_rows=disagreement_rows,
        failures=failures,
        extra_summary=extra_summary,
    )
    evidence_path = out / "experiment_evidence.json"
    evidence_path.write_bytes(serialize_experiment_evidence(bundle))
    evidence_store = R2ExperimentEvidenceStore.from_env()
    try:
        persisted = evidence_store.persist(bundle)
        durable_evidence = {
            "status": "PERSISTED",
            "key": persisted.key,
            "sha256": persisted.sha256,
            "bytes": persisted.bytes,
            "etag": persisted.etag,
        }
    except ExperimentEvidenceError as exc:
        if "already exists" not in str(exc):
            raise
        durable_evidence = {
            "status": "ALREADY_EXISTS",
            "key": evidence_store.key_for(run_date=run_date, run_id=args.run_id),
            "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            "bytes": evidence_path.stat().st_size,
        }

    summary = {
        "status": "PASS" if not failures else "PASS_WITH_LLM_FAILURES",
        "shadow_only": True,
        "production_authority_unchanged": True,
        "run_id": args.run_id,
        "model": args.model,
        "candidate_profile_version": profile_version,
        "routing": route_stats,
        "triage_decisions": dict(triage_decisions),
        "full_evaluation": full_stats,
        "rescue_reject_audit": audit_stats,
        "report": {
            "main_rows": len(report_rows.main),
            "llm_rescued_rows": len(report_rows.llm_rescued),
            "disagreement_rows": len(report_rows.disagreements),
            "path": str(out / "llm_shadow_report.xlsx"),
        },
        "failures": len(failures),
        "durable_cache": cache_sync,
        "durable_evidence": durable_evidence,
    }
    _write_json(out / "shadow_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
