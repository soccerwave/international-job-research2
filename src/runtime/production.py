from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from src.runtime.artifacts import atomic_create_bytes, verify_shard_bundle
from src.runtime.canonicalizer import canonicalize_records
from src.runtime.preprod import (
    _validate_canonical,
    apply_central_availability,
    collect_source_diagnostics,
    evaluate_canonical_records,
    run_preprod_finalization,
)
from src.runtime.state_projection import build_state_identity_projection
from src.state.r2_store import R2StateStore

PRODUCTION_CONTRACT_VERSION = "PRODUCTION_RUNTIME_V1.0.0"
PRODUCTION_STATE_KEY = "state/current/state.json"


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _canonical_id_digest(records: list[dict[str, Any]]) -> str:
    canonical_ids = sorted(str(record.get("canonical_id") or "") for record in records)
    payload = "\n".join(canonical_ids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assert_production_store(store: R2StateStore) -> None:
    """Production must use the authoritative unprefixed Stage 8 state key."""
    if str(getattr(store, "prefix", "") or "").strip("/"):
        raise RuntimeError("Production R2 state must be unprefixed; acceptance/test prefixes are forbidden")
    if store.current_key != PRODUCTION_STATE_KEY:
        raise RuntimeError(
            f"Unexpected production state key {store.current_key!r}; expected {PRODUCTION_STATE_KEY!r}"
        )


def strict_production_preflight(
    *,
    run_id: str,
    artifact_root: Path,
    observed_at: str,
    expected_shards: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Validate a first-production candidate without mutating durable state.

    This gate deliberately repeats canonical/evaluator/identity preparation in memory so
    a bad first collection cannot bootstrap the authoritative state object.

    Shards are consumed in the same deterministic directory-name order used by the frozen
    Stage 4 finalizer. This is required because Stage 10 canonicalization is intentionally
    frozen and its greedy clustering can be order-sensitive for ambiguous transitive matches.
    """
    expected = list(dict.fromkeys(expected_shards))
    run_dir = artifact_root / run_id / "shards"
    records: list[dict[str, Any]] = []
    failures: list[str] = []
    present: list[str] = []

    manifest_paths = sorted(run_dir.glob("*/manifest.json")) if run_dir.exists() else []
    manifest_shards = [path.parent.name for path in manifest_paths]
    expected_set = set(expected)
    unexpected = sorted(shard_id for shard_id in manifest_shards if shard_id not in expected_set)
    if unexpected:
        failures.append("unexpected shard(s): " + ", ".join(unexpected))

    # Match src.runtime.finalizer.finalize_run exactly: sorted shard directory name.
    for shard_id in sorted(expected):
        shard_dir = run_dir / shard_id
        if not (shard_dir / "manifest.json").exists():
            failures.append(f"missing shard: {shard_id}")
            continue
        present.append(shard_id)
        try:
            manifest, shard_records, diagnostics = verify_shard_bundle(shard_dir)
        except Exception as exc:
            failures.append(f"invalid shard {shard_id}: {type(exc).__name__}: {exc}")
            continue
        if manifest.status.value != "OK":
            failures.append(f"non-OK shard {shard_id}: {manifest.status.value}")
        source_results = (diagnostics.get("metadata") or {}).get("source_results") or []
        for item in source_results:
            status = str(item.get("status") or "UNKNOWN").upper()
            if status != "OK":
                failures.append(
                    f"non-OK source {item.get('report_key') or item.get('source_id') or 'unknown'}: {status}"
                )
        records.extend(shard_records)

    source_diagnostics = collect_source_diagnostics(run_id=run_id, artifact_root=artifact_root)
    degraded = sorted(
        key
        for key, item in source_diagnostics.items()
        if str(item.get("status") or "UNKNOWN").upper() in {"PARTIAL", "ERROR"}
    )
    unknown = sorted(
        key
        for key, item in source_diagnostics.items()
        if str(item.get("status") or "UNKNOWN").upper() == "UNKNOWN"
    )
    if degraded:
        failures.append("degraded source health: " + ", ".join(degraded))
    if unknown:
        failures.append("unknown source health: " + ", ".join(unknown))
    if not records:
        failures.append("zero accepted records")

    canonical_count = 0
    canonical_ids_sha256 = ""
    projection_summary: dict[str, Any] = {}
    if not failures:
        canonical, _ = canonicalize_records(records)
        for record in canonical:
            apply_central_availability(record, observed_at=observed_at)
        evaluate_canonical_records(canonical)
        _validate_canonical(canonical)
        projected, projection_summary = build_state_identity_projection(canonical)
        canonical_count = len(canonical)
        canonical_ids_sha256 = _canonical_id_digest(canonical)
        if not canonical:
            failures.append("zero canonical records")
        if len(projected) != len(canonical):
            failures.append("state projection changed record cardinality")
        if int(projection_summary.get("remaining_cross_record_alias_collisions") or 0) != 0:
            failures.append("state identity projection retains cross-record alias collisions")

    return {
        "status": "PASS" if not failures else "FAIL",
        "run_id": run_id,
        "expected_shards": len(expected),
        "present_shards": len(present),
        "unexpected_shards": unexpected,
        "raw_records": len(records),
        "canonical_records": canonical_count,
        "canonical_ids_sha256": canonical_ids_sha256,
        "record_order_policy": "SORTED_SHARD_DIRECTORY_NAME_MATCHES_FINALIZER",
        "degraded_sources": degraded,
        "unknown_sources": unknown,
        "projection": projection_summary,
        "failures": failures,
    }


def validate_strict_release_result(
    result: dict[str, Any],
    *,
    state_before_exists: bool,
) -> dict[str, bool]:
    canonical_count = int((result.get("canonicalization") or {}).get("canonical_records") or 0)
    state = result.get("state") or {}
    reporting = result.get("reporting") or {}
    source_health = reporting.get("source_health") or {}
    persistence = result.get("persistence") or {}
    consistency = result.get("consistency") or {}

    checks: dict[str, bool] = {
        "status_pass": result.get("status") == "PASS",
        "no_missing_shards": not result.get("missing_shards"),
        "no_degraded_sources": not result.get("degraded_sources"),
        "no_unknown_source_health": int(source_health.get("UNKNOWN") or 0) == 0,
        "canonical_records_positive": canonical_count > 0,
        "state_observed_matches_canonical": int(state.get("records_observed") or 0) == canonical_count,
        "state_identity_cardinality": bool(consistency.get("state_id_cardinality_matches_canonical")),
        "absence_never_inferred_closed": int(consistency.get("absence_inferred_closed") or 0) == 0,
        "authoritative_state_key": persistence.get("current_key") == PRODUCTION_STATE_KEY,
    }
    if not state_before_exists:
        checks.update(
            {
                "fresh_bootstrap_all_new": int(state.get("NEW") or 0) == canonical_count,
                "fresh_bootstrap_state_jobs": int(state.get("state_jobs") or 0) == canonical_count,
                "fresh_bootstrap_no_material_changes": int(state.get("MATERIALLY_CHANGED") or 0) == 0,
                "fresh_bootstrap_no_reopened": int(state.get("REOPENED") or 0) == 0,
            }
        )
    return checks


def run_production_finalization(
    *,
    run_id: str,
    artifact_root: Path,
    output_root: Path,
    observed_at: str,
    store: R2StateStore,
    expected_shards: list[str] | tuple[str, ...],
    allow_bootstrap: bool = False,
    strict_release: bool = False,
) -> dict[str, Any]:
    """Run the accepted Stage 10 core against authoritative production state."""
    assert_production_store(store)
    state_before = store.load_current(allow_missing=True)
    if not state_before.exists and not allow_bootstrap:
        raise RuntimeError(
            "Production state is missing. The first live release must explicitly allow bootstrap."
        )

    preflight: dict[str, Any] | None = None
    if strict_release:
        preflight = strict_production_preflight(
            run_id=run_id,
            artifact_root=artifact_root,
            observed_at=observed_at,
            expected_shards=expected_shards,
        )
        if preflight.get("status") != "PASS":
            production_dir = output_root / run_id / "production"
            production_dir.mkdir(parents=True, exist_ok=True)
            failed = {
                "contract_version": PRODUCTION_CONTRACT_VERSION,
                "run_id": run_id,
                "status": "STRICT_PREFLIGHT_FAILED",
                "state_before_exists": state_before.exists,
                "state_before_generation": int(state_before.state.get("generation") or 0),
                "state_write": "SKIPPED_BEFORE_MUTATION",
                "strict_preflight": preflight,
            }
            atomic_create_bytes(production_dir / "production_summary.json", _json_bytes(failed))
            return failed

    core = run_preprod_finalization(
        run_id=run_id,
        artifact_root=artifact_root,
        output_root=output_root,
        observed_at=observed_at,
        state_backend="R2",
        r2_store=store,
        allow_bootstrap=allow_bootstrap,
        expected_shards=expected_shards,
    )
    if (core.get("persistence") or {}).get("current_key") != PRODUCTION_STATE_KEY:
        raise RuntimeError("Production finalizer did not publish to the authoritative state key")

    strict_checks: dict[str, bool] | None = None
    if strict_release:
        strict_checks = validate_strict_release_result(core, state_before_exists=state_before.exists)
        core_canonical_count = int((core.get("canonicalization") or {}).get("canonical_records") or 0)
        canonical_path = output_root / run_id / "preprod" / "canonical_records.json"
        core_canonical_records = json.loads(canonical_path.read_text(encoding="utf-8"))
        strict_checks["preflight_canonical_count_matches_core"] = (
            int((preflight or {}).get("canonical_records") or 0) == core_canonical_count
        )
        strict_checks["preflight_canonical_ids_match_core"] = (
            str((preflight or {}).get("canonical_ids_sha256") or "")
            == _canonical_id_digest(core_canonical_records)
        )
        if not all(strict_checks.values()):
            raise RuntimeError("Strict V1 release checks failed: " + json.dumps(strict_checks, sort_keys=True))

    production_dir = output_root / run_id / "production"
    production_dir.mkdir(parents=True, exist_ok=True)
    frozen_core_dir = output_root / run_id / "preprod"
    copied: list[str] = []
    for name in (
        "academic_job_report.xlsx",
        "report_summary.json",
        "canonical_records.json",
        "preprod_summary.json",
    ):
        source = frozen_core_dir / name
        if source.exists():
            shutil.copy2(source, production_dir / name)
            copied.append(name)

    summary = {
        "contract_version": PRODUCTION_CONTRACT_VERSION,
        "run_id": run_id,
        "status": core.get("status"),
        "state_before_exists": state_before.exists,
        "state_before_generation": int(state_before.state.get("generation") or 0),
        "authoritative_state_key": PRODUCTION_STATE_KEY,
        "strict_release": strict_release,
        "strict_preflight": preflight,
        "strict_checks": strict_checks,
        "copied_outputs": copied,
        "core_contract_version": core.get("contract_version"),
        "core_result": core,
    }
    atomic_create_bytes(production_dir / "production_summary.json", _json_bytes(summary))
    return summary
