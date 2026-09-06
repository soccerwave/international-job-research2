from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.reporting.report import build_reporting_payload
from src.runtime.production import _canonical_id_digest, strict_production_preflight
from src.runtime.production_reporting import BASELINE_EVENT, mark_baseline_existing


ROOT = Path(__file__).resolve().parents[1]


class V1LiveBootstrapFixTests(unittest.TestCase):
    def test_state_jobs_install_both_frozen_runtime_and_cloud_requirements(self):
        expected = "python -m pip install --disable-pip-version-check -r requirements.txt -r requirements-cloud.txt"
        production = (ROOT / ".github" / "workflows" / "production.yml").read_text(encoding="utf-8")
        recovery = (ROOT / ".github" / "workflows" / "recover-production-state.yml").read_text(encoding="utf-8")
        ci = (ROOT / ".github" / "workflows" / "test-v1.yml").read_text(encoding="utf-8")
        self.assertIn(expected, production)
        self.assertIn(expected, recovery)
        self.assertIn(expected, ci)

    def test_first_bootstrap_reporting_marks_records_baseline_existing_without_mutating_input(self):
        original = [
            {
                "source_record_id": "job-1",
                "raw_extra": {
                    "state": {
                        "seen_status": "NEW",
                        "change_reasons": ["seed"],
                    }
                },
            }
        ]
        before = copy.deepcopy(original)
        baseline = mark_baseline_existing(original)
        self.assertEqual(original, before)
        self.assertEqual(baseline[0]["raw_extra"]["state"]["seen_status"], BASELINE_EVENT)
        self.assertEqual(baseline[0]["raw_extra"]["state"]["change_reasons"], [])

    def test_baseline_existing_is_not_a_stage9_change_event(self):
        from src.reporting.report import CHANGE_EVENTS

        self.assertNotIn(BASELINE_EVENT, CHANGE_EVENTS)

    def test_baseline_existing_suppresses_today_but_preserves_current_actionable(self):
        records = [
            {
                "source_record_id": "job-1",
                "source": {
                    "source_key": "test-source",
                    "provider": "Test Source",
                    "source_status": "OPEN",
                    "detail_url": "https://example.org/job/1",
                },
                "position": {"title_raw": "Postdoctoral Researcher"},
                "location": {"country_code": "DE"},
                "dates": {},
                "description": {"detail_status": "FULL"},
                "raw_extra": {
                    "state": {"seen_status": "NEW", "lifecycle_status": "OPEN"},
                    "evaluation": {
                        "recommendation": "APPLY",
                        "pre_evaluation_disposition": "ELIGIBLE_FOR_EVALUATION",
                        "dimensions": {},
                    },
                },
            }
        ]
        payload = build_reporting_payload(mark_baseline_existing(records), run_id="bootstrap-test")
        self.assertEqual(payload["summary"]["current_actionable"], 1)
        self.assertEqual(payload["summary"]["today_actionable"], 0)
        self.assertEqual(len(payload["today_actionable"]), 0)

    def test_finalizer_cli_rebuilds_only_fresh_successful_bootstrap_outputs(self):
        script = (ROOT / "scripts" / "run_production_finalizer.py").read_text(encoding="utf-8")
        self.assertIn('result.get("state_before_exists") is False', script)
        self.assertIn('rebuild_fresh_bootstrap_report', script)
        self.assertIn('== "PASS"', script)

    def test_canonical_id_digest_is_order_independent(self):
        records = [{"canonical_id": "vac_b"}, {"canonical_id": "vac_a"}]
        self.assertEqual(_canonical_id_digest(records), _canonical_id_digest(list(reversed(records))))

    def test_strict_preflight_uses_same_sorted_shard_order_as_frozen_finalizer(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp)
            run_id = "order-test"
            for shard_id in ("z-shard", "a-shard"):
                shard_dir = artifact_root / run_id / "shards" / shard_id
                shard_dir.mkdir(parents=True, exist_ok=True)
                (shard_dir / "manifest.json").write_text("{}\n", encoding="utf-8")

            observed_order: list[str] = []

            def fake_verify(shard_dir: Path):
                shard_id = shard_dir.name
                manifest = SimpleNamespace(status=SimpleNamespace(value="OK"))
                record = {"source_record_id": shard_id, "canonical_id": f"vac_{shard_id}"}
                diagnostics = {
                    "metadata": {
                        "source_results": [
                            {"status": "OK", "report_key": shard_id}
                        ]
                    }
                }
                return manifest, [record], diagnostics

            def fake_canonicalize(records):
                observed_order.extend(str(record["source_record_id"]) for record in records)
                return list(records), {"canonical_records": len(records)}

            projection_summary = {"remaining_cross_record_alias_collisions": 0}
            source_health = {
                "a-shard": {"status": "OK"},
                "z-shard": {"status": "OK"},
            }
            with (
                patch("src.runtime.production.verify_shard_bundle", side_effect=fake_verify),
                patch("src.runtime.production.collect_source_diagnostics", return_value=source_health),
                patch("src.runtime.production.canonicalize_records", side_effect=fake_canonicalize),
                patch("src.runtime.production.apply_central_availability"),
                patch("src.runtime.production.evaluate_canonical_records"),
                patch("src.runtime.production._validate_canonical"),
                patch(
                    "src.runtime.production.build_state_identity_projection",
                    side_effect=lambda records: (list(records), projection_summary),
                ),
            ):
                result = strict_production_preflight(
                    run_id=run_id,
                    artifact_root=artifact_root,
                    observed_at="2026-09-05T00:00:00+00:00",
                    expected_shards=["z-shard", "a-shard"],
                )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(observed_order, ["a-shard", "z-shard"])
            self.assertEqual(
                result["record_order_policy"],
                "SORTED_SHARD_DIRECTORY_NAME_MATCHES_FINALIZER",
            )
            self.assertEqual(result["unexpected_shards"], [])

    def test_strict_preflight_rejects_unexpected_shard_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp)
            run_id = "unexpected-test"
            for shard_id in ("a-shard", "extra-shard"):
                shard_dir = artifact_root / run_id / "shards" / shard_id
                shard_dir.mkdir(parents=True, exist_ok=True)
                (shard_dir / "manifest.json").write_text("{}\n", encoding="utf-8")

            manifest = SimpleNamespace(status=SimpleNamespace(value="OK"))
            with (
                patch(
                    "src.runtime.production.verify_shard_bundle",
                    return_value=(manifest, [{"canonical_id": "vac_a"}], {"metadata": {"source_results": []}}),
                ),
                patch(
                    "src.runtime.production.collect_source_diagnostics",
                    return_value={"a-shard": {"status": "OK"}},
                ),
            ):
                result = strict_production_preflight(
                    run_id=run_id,
                    artifact_root=artifact_root,
                    observed_at="2026-09-05T00:00:00+00:00",
                    expected_shards=["a-shard"],
                )

            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["unexpected_shards"], ["extra-shard"])
            self.assertTrue(any("unexpected shard" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
