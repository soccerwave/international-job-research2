from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.run_production_finalizer as production_finalizer_cli
from src.runtime.artifacts import write_shard_bundle
from src.runtime.contracts import ShardDiagnostic, ShardStatus
from src.runtime.observability import collect_run_observability


class Stage51RunObservabilityTests(unittest.TestCase):
    def _write(
        self,
        root: Path,
        *,
        run_id: str,
        shard_id: str,
        source_id: str,
        report_key: str,
        elapsed_ms: int,
        records: int,
        status: ShardStatus = ShardStatus.OK,
        source_status: str = "OK",
        warnings: list[str] | None = None,
        error: str = "",
        include_source_results: bool = True,
    ) -> None:
        warnings = list(warnings or [])
        metadata = {"production_run": True}
        if include_source_results:
            metadata["source_results"] = [
                {
                    "source_id": source_id,
                    "report_key": report_key,
                    "status": source_status,
                    "records": records,
                    "elapsed_ms": elapsed_ms,
                    "warnings": warnings,
                    "error": error,
                }
            ]
        diagnostic = ShardDiagnostic(
            shard_id=shard_id,
            source_ids=[source_id],
            status=status,
            started_at="2026-09-06T18:00:00+00:00",
            finished_at="2026-09-06T18:00:01+00:00",
            elapsed_ms=elapsed_ms,
            records_observed=records,
            records_emitted=records,
            detail_attempted=records,
            detail_succeeded=records,
            warnings=warnings,
            errors=[error] if error else [],
            metadata=metadata,
        )
        write_shard_bundle(
            root=root,
            run_id=run_id,
            shard_id=shard_id,
            source_ids=[source_id],
            records=[{"source": {"source_key": source_id}} for _ in range(records)],
            diagnostic=diagnostic,
            producer_version="TEST",
        )

    def test_logical_source_aggregates_multiple_runtime_shards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, run_id="r1", shard_id="linkedin-europe-germany", source_id="linkedin_europe", report_key="linkedin_mads", elapsed_ms=1200, records=2)
            self._write(root, run_id="r1", shard_id="linkedin-europe-west", source_id="linkedin_europe", report_key="linkedin_mads", elapsed_ms=800, records=3)
            result = collect_run_observability(
                run_id="r1",
                artifact_root=root,
                expected_shards=("linkedin-europe-germany", "linkedin-europe-west"),
            )
            self.assertEqual(len(result["sources"]), 1)
            source = result["sources"][0]
            self.assertEqual(source["logical_source"], "linkedin_mads")
            self.assertEqual(source["records"], 5)
            self.assertEqual(source["elapsed_ms"], 2000)
            self.assertEqual(source["shard_ids"], ["linkedin-europe-germany", "linkedin-europe-west"])
            self.assertEqual(len(source["instances"]), 2)

    def test_missing_expected_shard_is_explicit_not_inferred_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, run_id="r2", shard_id="thematic", source_id="ecss", report_key="ecss", elapsed_ms=300, records=1)
            result = collect_run_observability(
                run_id="r2",
                artifact_root=root,
                expected_shards=("thematic", "corehr-ireland"),
            )
            self.assertEqual(result["missing_shards"], ["corehr-ireland"])
            missing = next(row for row in result["shards"] if row["shard_id"] == "corehr-ireland")
            self.assertEqual(missing["status"], "MISSING")
            self.assertEqual(missing["errors"], ["MISSING_SHARD_ARTIFACT"])

    def test_unexpected_shard_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, run_id="r3", shard_id="expected", source_id="one", report_key="one", elapsed_ms=1, records=0)
            self._write(root, run_id="r3", shard_id="unexpected", source_id="two", report_key="two", elapsed_ms=2, records=0)
            result = collect_run_observability(run_id="r3", artifact_root=root, expected_shards=("expected",))
            self.assertEqual(result["unexpected_shards"], ["unexpected"])
            self.assertEqual({row["shard_id"] for row in result["shards"]}, {"expected", "unexpected"})

    def test_partial_source_preserves_warning_error_and_elapsed_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(
                root,
                run_id="r4",
                shard_id="portal",
                source_id="jobs_ac_uk",
                report_key="jobs_ac_uk",
                elapsed_ms=456,
                records=2,
                status=ShardStatus.PARTIAL,
                source_status="PARTIAL",
                warnings=["Incomplete coverage"],
                error="HTTPError: 503",
            )
            result = collect_run_observability(run_id="r4", artifact_root=root, expected_shards=("portal",))
            source = result["sources"][0]
            self.assertEqual(source["status"], "PARTIAL")
            self.assertEqual(source["elapsed_ms"], 456)
            self.assertEqual(source["warning_count"], 1)
            self.assertEqual(source["error_count"], 1)
            self.assertEqual(source["instances"][0]["shard_id"], "portal")

    def test_totals_expose_record_detail_and_elapsed_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, run_id="r5", shard_id="a", source_id="a", report_key="a", elapsed_ms=100, records=2)
            self._write(root, run_id="r5", shard_id="b", source_id="b", report_key="b", elapsed_ms=200, records=3)
            result = collect_run_observability(run_id="r5", artifact_root=root, expected_shards=("a", "b"))
            self.assertEqual(result["totals"]["records_observed"], 5)
            self.assertEqual(result["totals"]["records_emitted"], 5)
            self.assertEqual(result["totals"]["detail_attempted"], 5)
            self.assertEqual(result["totals"]["detail_succeeded"], 5)
            self.assertEqual(result["totals"]["shard_elapsed_ms_sum"], 300)
            self.assertEqual(result["totals"]["source_elapsed_ms_sum"], 300)

    def test_finalizer_cli_persists_run_observability_in_production_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_result = {
                "status": "PASS",
                "state_before_exists": True,
                "core_result": {"status": "PASS"},
            }
            observability = {"version": 1, "run_id": "r6", "shards": [], "sources": []}
            argv = [
                "run_production_finalizer.py",
                "--run-id",
                "r6",
                "--artifact-root",
                str(root),
                "--output-root",
                str(root),
            ]
            with patch.object(sys, "argv", argv), \
                 patch.object(production_finalizer_cli.R2StateStore, "from_env", return_value=object()), \
                 patch.object(production_finalizer_cli, "run_production_finalization", return_value=dict(base_result)), \
                 patch.object(production_finalizer_cli, "collect_run_observability", return_value=observability):
                exit_code = production_finalizer_cli.main()
            self.assertEqual(exit_code, 0)
            summary = json.loads((root / "r6" / "production" / "production_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["run_observability"], observability)


if __name__ == "__main__":
    unittest.main()
