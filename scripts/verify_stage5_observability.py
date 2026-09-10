from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.runtime.artifacts import write_shard_bundle
from src.runtime.contracts import ShardDiagnostic, ShardStatus
from src.runtime.observability import collect_run_observability

FREEZE = ROOT / "RELEASE_FREEZE_V1.1.0.json"


def _require(condition: bool, label: str, checks: dict[str, bool]) -> None:
    checks[label] = bool(condition)
    if not condition:
        raise AssertionError(label)


def _write_lifecycle(root: Path, run_id: str, shard_id: str, events: list[dict]) -> None:
    target = root / run_id / "diagnostics" / shard_id / "source_lifecycle.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")


def _write_bundle(
    root: Path,
    run_id: str,
    shard_id: str,
    source_id: str,
    status: ShardStatus,
    *,
    failure_class: str = "",
    error: str = "",
) -> None:
    source_status = status.value
    diagnostic = ShardDiagnostic(
        shard_id=shard_id,
        source_ids=[source_id],
        status=status,
        started_at="2026-09-10T00:00:00+00:00",
        finished_at="2026-09-10T00:00:01+00:00",
        elapsed_ms=1000,
        records_observed=0,
        records_emitted=0,
        warnings=[],
        errors=[f"{source_id}: {error}"] if error else [],
        metadata={
            "source_results": [
                {
                    "source_id": source_id,
                    "report_key": source_id,
                    "status": source_status,
                    "records": 0,
                    "elapsed_ms": 1000,
                    "warnings": [],
                    "error": error,
                    "failure_class": failure_class,
                }
            ]
        },
    )
    write_shard_bundle(
        root=root,
        run_id=run_id,
        shard_id=shard_id,
        source_ids=[source_id],
        records=[],
        diagnostic=diagnostic,
        producer_version="STAGE5_6_CERTIFICATION",
    )


def main() -> int:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    obs = freeze["run_observability"]
    checks: dict[str, bool] = {}

    _require(obs.get("status") == "LIVE_VALIDATED_FINALIZER_WIRED", "stage5_1_finalizer_wired", checks)
    _require(obs.get("stall_detection") == "LIVE_VALIDATED_STAGE_5_2", "stage5_2_live_validated", checks)
    _require(
        obs.get("failure_taxonomy") == "GITHUB_ACTIONS_VALIDATED_STAGE_5_3",
        "stage5_3_failure_taxonomy_validated",
        checks,
    )
    _require(
        obs.get("artifact_durability") == "LIVE_VALIDATED_STAGE_5_4",
        "stage5_4_artifact_durability_validated",
        checks,
    )
    _require(
        obs.get("runtime_anomaly_detection") == "GITHUB_ACTIONS_VALIDATED_STAGE_5_5",
        "stage5_5_anomaly_detection_validated",
        checks,
    )
    _require(obs.get("runtime_anomaly_detection_behavior") == "OBSERVE_ONLY", "stage5_5_observe_only", checks)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        clean_run = "stage5-6-clean"
        _write_bundle(root, clean_run, "clean-shard", "clean-source", ShardStatus.OK)
        _write_lifecycle(
            root,
            clean_run,
            "clean-shard",
            [
                {"event": "source_start", "source_id": "clean-source", "report_key": "clean-source"},
                {"event": "source_waiting", "source_id": "clean-source", "report_key": "clean-source"},
                {"event": "source_done", "source_id": "clean-source", "report_key": "clean-source"},
            ],
        )
        clean = collect_run_observability(
            run_id=clean_run,
            artifact_root=root,
            expected_shards=("clean-shard",),
        )
        _require(clean["source_status_counts"] == {"OK": 1}, "clean_source_status_visible", checks)
        _require(clean["runtime_anomalies"]["status"] == "NO_ANOMALIES", "clean_run_no_anomalies", checks)

        error_run = "stage5-6-error"
        _write_bundle(
            root,
            error_run,
            "error-shard",
            "error-source",
            ShardStatus.ERROR,
            failure_class="TIMEOUT",
            error="TimeoutError: timed out",
        )
        _write_lifecycle(
            root,
            error_run,
            "error-shard",
            [
                {"event": "source_start", "source_id": "error-source", "report_key": "error-source"},
                {
                    "event": "source_error",
                    "source_id": "error-source",
                    "report_key": "error-source",
                    "failure_class": "TIMEOUT",
                    "error_type": "TimeoutError",
                },
                {"event": "source_done", "source_id": "error-source", "report_key": "error-source"},
            ],
        )
        error = collect_run_observability(
            run_id=error_run,
            artifact_root=root,
            expected_shards=("error-shard",),
        )
        _require(error["failure_class_counts"] == {"TIMEOUT": 1}, "failure_class_visible", checks)
        _require(error["runtime_anomalies"]["code_counts"].get("SOURCE_ERROR") == 1, "source_error_anomaly_visible", checks)
        _require(
            error["runtime_anomalies"]["code_counts"].get("LIFECYCLE_SOURCE_ERROR") == 1,
            "lifecycle_error_anomaly_visible",
            checks,
        )

        missing_run = "stage5-6-missing"
        missing = collect_run_observability(
            run_id=missing_run,
            artifact_root=root,
            expected_shards=("missing-shard",),
        )
        _require(missing["missing_shards"] == ["missing-shard"], "missing_shard_visible", checks)
        _require(
            missing["runtime_anomalies"]["code_counts"].get("MISSING_SHARD_ARTIFACT") == 1,
            "missing_shard_anomaly_visible",
            checks,
        )

        incomplete_run = "stage5-6-incomplete"
        _write_lifecycle(
            root,
            incomplete_run,
            "interrupted-shard",
            [{"event": "source_start", "source_id": "interrupted-source", "report_key": "interrupted-source"}],
        )
        incomplete = collect_run_observability(
            run_id=incomplete_run,
            artifact_root=root,
            expected_shards=("interrupted-shard",),
        )
        _require(
            incomplete["runtime_anomalies"]["code_counts"].get("INCOMPLETE_SOURCE_LIFECYCLE") == 1,
            "interrupted_lifecycle_visible",
            checks,
        )
        _require(
            incomplete["runtime_anomalies"]["code_counts"].get("MISSING_SHARD_ARTIFACT") == 1,
            "diagnostics_only_missing_bundle_semantics_preserved",
            checks,
        )

    result = {
        "status": "PASS",
        "profile": "STAGE_5_OBSERVABILITY_CERTIFICATION",
        "checks": checks,
        "substage_evidence": {
            "stage5_1_validation_run_id": obs.get("validation_run_id"),
            "stage5_2_live_run_id": obs.get("stall_detection_live_run_id"),
            "stage5_3_ci_run_id": obs.get("failure_taxonomy_ci_run_id"),
            "stage5_4_live_run_id": obs.get("artifact_durability_live_run_id"),
            "stage5_5_ci_run_id": obs.get("runtime_anomaly_detection_ci_run_id"),
        },
        "behavior": "READ_ONLY_CERTIFICATION",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
