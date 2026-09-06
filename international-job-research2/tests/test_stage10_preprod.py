from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.runtime.artifacts import write_shard_bundle
from src.runtime.canonicalizer import canonicalize_records
from src.runtime.contracts import ShardDiagnostic, ShardStatus
from src.runtime.preprod import (
    apply_central_availability,
    collect_source_diagnostics,
    evaluate_canonical_records,
    run_preprod_finalization,
)
from src.state.engine import load_state
from tests.test_stage7_evaluator import base_job


def _job(
    job_id: str,
    *,
    source_key: str = "fixture_direct",
    source_kind: str = "DIRECT_INSTITUTION",
    url: str | None = None,
    title: str = "Postdoctoral Researcher in Exercise Physiology",
    detail: str | None = None,
) -> dict:
    record = base_job(title=title, jd=detail if detail is not None else "")
    record["source_record_id"] = f"{source_key}:{job_id}"
    record["canonical_id"] = None
    record["record_stage"] = "SHARD_ENRICHED"
    record["source"].update({
        "source_key": source_key,
        "source_kind": source_kind,
        "provider": "Fixture University",
        "source_job_id": job_id,
        "listing_url": url or f"https://example.org/{source_key}/jobs/{job_id}",
        "detail_url": url or f"https://example.org/{source_key}/jobs/{job_id}",
        "apply_url": (url or f"https://example.org/{source_key}/jobs/{job_id}") + "/apply",
        "source_status": "OPEN",
    })
    record["provenance"] = {
        "observed_by_sources": [source_key],
        "raw_payload_fingerprint": None,
        "notes": [],
    }
    record["classification"]["review_codes"] = ["COLLECTOR_ONLY_NOT_PRE_EVALUATED"]
    record["classification"]["pre_evaluation_disposition"] = "POLICY_REVIEW"
    return record


def _full_detail() -> str:
    return (
        "We seek a postdoctoral researcher with a PhD in exercise physiology. "
        "The project studies physical activity, fitness, exercise neuroscience, stress biology, "
        "cognition and human exercise interventions. Experience with randomized controlled trials, "
        "physiological assessment and statistics is desirable. "
    ) * 8


def _diagnostic(
    shard_id: str,
    source_ids: list[str],
    status: ShardStatus,
    *,
    records: int,
    source_results: list[dict] | None = None,
) -> ShardDiagnostic:
    return ShardDiagnostic(
        shard_id=shard_id,
        source_ids=source_ids,
        status=status,
        started_at="2026-09-04T20:00:00+00:00",
        finished_at="2026-09-04T20:00:01+00:00",
        elapsed_ms=1000,
        records_observed=records,
        records_emitted=records,
        warnings=[],
        errors=["synthetic failure"] if status == ShardStatus.ERROR else [],
        metadata={"source_results": source_results or []},
    )


def _write_bundle(root: Path, run_id: str, shard_id: str, records: list[dict], *, status: ShardStatus = ShardStatus.OK, source_ids: list[str] | None = None, source_results: list[dict] | None = None) -> None:
    ids = source_ids or [shard_id]
    write_shard_bundle(
        root=root,
        run_id=run_id,
        shard_id=shard_id,
        source_ids=ids,
        records=records,
        diagnostic=_diagnostic(shard_id, ids, status, records=len(records), source_results=source_results),
        producer_version="stage10-test",
    )


class Stage10CanonicalizationTests(unittest.TestCase):
    def test_resolved_cross_source_duplicate_merges_and_aggregates_provenance(self):
        detail = _full_detail()
        direct = _job("A1", source_key="direct", source_kind="DIRECT_INSTITUTION", detail=detail)
        shared = _job("B9", source_key="euraxess", source_kind="SHARED_AGGREGATOR", detail=detail)
        shared["source"]["listing_url"] = "https://euraxess.example/jobs/B9"
        shared["source"]["detail_url"] = "https://euraxess.example/jobs/B9"
        shared["source"]["apply_url"] = "https://euraxess.example/jobs/B9/apply"

        canonical, summary = canonicalize_records([shared, direct])

        self.assertEqual(len(canonical), 1)
        self.assertEqual(summary["duplicates_removed"], 1)
        self.assertEqual(canonical[0]["source"]["source_key"], "direct")
        self.assertEqual(set(canonical[0]["provenance"]["observed_by_sources"]), {"direct", "euraxess"})
        self.assertEqual(canonical[0]["record_stage"], "CANONICALIZED")
        self.assertTrue(canonical[0]["canonical_id"].startswith("vac_"))

    def test_same_source_distinct_ids_never_merge(self):
        detail = _full_detail()
        a = _job("101", source_key="board", detail=detail)
        b = _job("102", source_key="board", detail=detail)
        canonical, summary = canonicalize_records([a, b])
        self.assertEqual(len(canonical), 2)
        self.assertEqual(summary["duplicates_removed"], 0)

    def test_distinct_reference_ids_prevent_false_merge(self):
        detail = _full_detail()
        a = _job("1", source_key="a", title="Postdoctoral Researcher REF-2026/100-ABC", detail=detail)
        b = _job("2", source_key="b", title="Postdoctoral Researcher REF-2026/101-ABC", detail=detail)
        canonical, _ = canonicalize_records([a, b])
        self.assertEqual(len(canonical), 2)

    def test_unresolved_cross_source_title_match_is_not_fuzzy_merged(self):
        a = _job("1", source_key="a", detail=None)
        b = _job("2", source_key="b", detail=None)
        self.assertEqual(a["description"]["detail_status"], "UNAVAILABLE")
        self.assertEqual(b["description"]["detail_status"], "UNAVAILABLE")
        canonical, summary = canonicalize_records([a, b])
        self.assertEqual(len(canonical), 2)
        self.assertEqual(summary["fail_open_unresolved_fuzzy_merge"], "DISABLED")

    def test_collector_sentinel_is_removed_before_evaluator(self):
        record = _job("1", detail=_full_detail())
        canonical, _ = canonicalize_records([record])
        evaluate_canonical_records(canonical)
        evaluation = canonical[0]["raw_extra"]["evaluation"]
        self.assertEqual(evaluation["recommendation"], "STRONG_APPLY")
        self.assertNotIn("COLLECTOR_ONLY_NOT_PRE_EVALUATED", evaluation["review_codes"])

    def test_explicit_deadline_evidence_controls_availability_not_absence(self):
        past = _job("past", detail=_full_detail())
        past["source"]["source_status"] = "UNKNOWN"
        past["dates"].update({"deadline_at": "2026-09-01T00:00:00+00:00", "deadline_status": "KNOWN"})
        apply_central_availability(past, observed_at="2026-09-04T20:00:00+00:00")
        self.assertEqual(past["source"]["source_status"], "CLOSED")
        self.assertEqual(past["raw_extra"]["availability"]["reason"], "EXPLICIT_DEADLINE_PASSED")

        future = _job("future", detail=_full_detail())
        future["source"]["source_status"] = "UNKNOWN"
        future["dates"].update({"deadline_at": "2026-10-01T00:00:00+00:00", "deadline_status": "KNOWN"})
        apply_central_availability(future, observed_at="2026-09-04T20:00:00+00:00")
        self.assertEqual(future["source"]["source_status"], "OPEN")


class Stage10EndToEndTests(unittest.TestCase):
    def test_full_local_path_builds_state_and_xlsx_from_same_canonical_set(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_id = "stage10-e2e-1"
            state_path = root / "state" / "current.json"
            detail = _full_detail()
            a = _job("A1", source_key="direct", source_kind="DIRECT_INSTITUTION", detail=detail)
            b = _job("B9", source_key="shared", source_kind="SHARED_AGGREGATOR", detail=detail)
            _write_bundle(root, run_id, "shard-a", [a], source_ids=["direct"])
            _write_bundle(root, run_id, "shard-b", [b], source_ids=["shared"])

            result = run_preprod_finalization(
                run_id=run_id,
                artifact_root=root,
                output_root=root,
                observed_at="2026-09-04T20:00:00+00:00",
                state_backend="LOCAL",
                state_path=state_path,
            )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["canonicalization"]["canonical_records"], 1)
            self.assertEqual(result["state"]["NEW"], 1)
            self.assertTrue(result["consistency"]["state_observed_matches_canonical"])
            self.assertEqual(result["consistency"]["absence_inferred_closed"], 0)
            canonical = json.loads((root / run_id / "preprod" / "canonical_records.json").read_text(encoding="utf-8"))
            self.assertEqual(canonical[0]["raw_extra"]["evaluation"]["recommendation"], "STRONG_APPLY")
            self.assertEqual(canonical[0]["raw_extra"]["state"]["seen_status"], "NEW")
            report = root / run_id / "preprod" / "academic_job_report.xlsx"
            with zipfile.ZipFile(report) as archive:
                workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
            self.assertIn('name="CURRENT_ACTIONABLE"', workbook_xml)

    def test_partial_run_preserves_unobserved_history_and_reports_failed_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "state" / "current.json"
            first = "stage10-history-1"
            second = "stage10-history-2"
            old_job = _job("old", source_key="healthy_old", detail=_full_detail())
            _write_bundle(root, first, "healthy-old", [old_job], source_ids=["healthy_old"])
            first_result = run_preprod_finalization(
                run_id=first,
                artifact_root=root,
                output_root=root,
                observed_at="2026-09-04T20:00:00+00:00",
                state_backend="LOCAL",
                state_path=state_path,
            )
            self.assertEqual(first_result["state"]["NEW"], 1)

            new_job = _job("new", source_key="healthy_new", detail=_full_detail())
            _write_bundle(root, second, "healthy-new", [new_job], source_ids=["healthy_new"])
            _write_bundle(
                root,
                second,
                "failed-source",
                [],
                status=ShardStatus.ERROR,
                source_ids=["failed_source"],
                source_results=[{"source_id": "failed_source", "report_key": "failed_source", "status": "ERROR", "records": 0, "warnings": [], "error": "timeout"}],
            )

            second_result = run_preprod_finalization(
                run_id=second,
                artifact_root=root,
                output_root=root,
                observed_at="2026-09-05T20:00:00+00:00",
                state_backend="LOCAL",
                state_path=state_path,
            )

            self.assertEqual(second_result["status"], "PARTIAL_PASS")
            self.assertEqual(second_result["state"]["not_observed_inferred_closed"], 0)
            self.assertEqual(second_result["source_diagnostics"]["failed_source"]["status"], "ERROR")
            state = load_state(state_path)
            self.assertEqual(len(state["jobs"]), 2)
            old_entries = [entry for entry in state["jobs"].values() if any("healthy_old" in alias for alias in entry["aliases"])]
            self.assertEqual(len(old_entries), 1)
            self.assertEqual(old_entries[0]["lifecycle_status"], "OPEN")

    def test_all_failed_run_skips_state_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_id = "stage10-all-failed"
            state_path = root / "state" / "current.json"
            _write_bundle(root, run_id, "failed", [], status=ShardStatus.ERROR, source_ids=["failed"])
            result = run_preprod_finalization(
                run_id=run_id,
                artifact_root=root,
                output_root=root,
                observed_at="2026-09-04T20:00:00+00:00",
                state_backend="LOCAL",
                state_path=state_path,
            )
            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(result["state_write"], "SKIPPED_NO_ACCEPTED_SHARDS")
            self.assertFalse(state_path.exists())

    def test_source_diagnostics_preserve_zero_observation_success(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_id = "stage10-zero"
            _write_bundle(
                root,
                run_id,
                "zero",
                [],
                source_ids=["zero_source"],
                source_results=[{"source_id": "zero_source", "report_key": "zero_source", "status": "OK", "records": 0, "warnings": ["zero observations"], "error": ""}],
            )
            diagnostics = collect_source_diagnostics(run_id=run_id, artifact_root=root)
            self.assertEqual(diagnostics["zero_source"]["status"], "OK")
            self.assertEqual(diagnostics["zero_source"]["records"], 0)
            self.assertIn("zero observations", diagnostics["zero_source"]["warnings"])


if __name__ == "__main__":
    unittest.main()
