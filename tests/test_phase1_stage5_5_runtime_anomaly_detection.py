from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.runtime.anomaly_detection import detect_runtime_anomalies


class Stage55RuntimeAnomalyDetectionTests(unittest.TestCase):
    def test_clean_runtime_has_no_anomalies(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_runtime_anomalies(
                run_id="clean",
                artifact_root=Path(tmp),
                shard_rows=[],
                source_rows=[],
                missing_shards=[],
                unexpected_shards=[],
            )
            self.assertEqual(result["status"], "NO_ANOMALIES")
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["behavior"], "OBSERVE_ONLY")

    def test_missing_and_unexpected_shards_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_runtime_anomalies(
                run_id="r1",
                artifact_root=Path(tmp),
                shard_rows=[],
                source_rows=[],
                missing_shards=["missing"],
                unexpected_shards=["extra"],
            )
            self.assertEqual(result["code_counts"]["MISSING_SHARD_ARTIFACT"], 1)
            self.assertEqual(result["code_counts"]["UNEXPECTED_SHARD_ARTIFACT"], 1)

    def test_source_error_is_flagged_without_changing_status(self):
        source_rows = [{
            "logical_source": "x",
            "instances": [{
                "shard_id": "s1",
                "source_id": "x",
                "status": "ERROR",
                "failure_class": "RATE_LIMIT",
            }],
        }]
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_runtime_anomalies(
                run_id="r2",
                artifact_root=Path(tmp),
                shard_rows=[],
                source_rows=source_rows,
                missing_shards=[],
                unexpected_shards=[],
            )
            self.assertEqual(result["code_counts"], {"SOURCE_ERROR": 1})
            self.assertEqual(result["items"][0]["detail"], "RATE_LIMIT")

    def test_incomplete_lifecycle_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "r3" / "diagnostics" / "s1" / "source_lifecycle.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "event": "source_start",
                "source_id": "source_a",
                "report_key": "source_a",
            }) + "\n", encoding="utf-8")
            result = detect_runtime_anomalies(
                run_id="r3",
                artifact_root=root,
                shard_rows=[],
                source_rows=[],
                missing_shards=[],
                unexpected_shards=[],
            )
            self.assertEqual(result["code_counts"], {"INCOMPLETE_SOURCE_LIFECYCLE": 1})

    def test_balanced_lifecycle_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "r4" / "diagnostics" / "s1" / "source_lifecycle.jsonl"
            path.parent.mkdir(parents=True)
            events = [
                {"event": "source_start", "source_id": "a", "report_key": "a"},
                {"event": "source_waiting", "source_id": "a", "report_key": "a"},
                {"event": "source_done", "source_id": "a", "report_key": "a"},
            ]
            path.write_text("\n".join(json.dumps(x) for x in events) + "\n", encoding="utf-8")
            result = detect_runtime_anomalies(
                run_id="r4",
                artifact_root=root,
                shard_rows=[],
                source_rows=[],
                missing_shards=[],
                unexpected_shards=[],
            )
            self.assertEqual(result["status"], "NO_ANOMALIES")

    def test_malformed_lifecycle_event_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "r5" / "diagnostics" / "s1" / "source_lifecycle.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text("{bad json}\n", encoding="utf-8")
            result = detect_runtime_anomalies(
                run_id="r5",
                artifact_root=root,
                shard_rows=[],
                source_rows=[],
                missing_shards=[],
                unexpected_shards=[],
            )
            self.assertEqual(result["code_counts"], {"MALFORMED_LIFECYCLE_EVENT": 1})

    def test_lifecycle_source_error_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "r6" / "diagnostics" / "s1" / "source_lifecycle.jsonl"
            path.parent.mkdir(parents=True)
            events = [
                {"event": "source_start", "source_id": "a", "report_key": "a"},
                {"event": "source_error", "source_id": "a", "report_key": "a", "failure_class": "TIMEOUT"},
                {"event": "source_done", "source_id": "a", "report_key": "a"},
            ]
            path.write_text("\n".join(json.dumps(x) for x in events) + "\n", encoding="utf-8")
            result = detect_runtime_anomalies(
                run_id="r6",
                artifact_root=root,
                shard_rows=[],
                source_rows=[],
                missing_shards=[],
                unexpected_shards=[],
            )
            self.assertEqual(result["code_counts"], {"LIFECYCLE_SOURCE_ERROR": 1})
            self.assertEqual(result["items"][0]["detail"], "TIMEOUT")


if __name__ == "__main__":
    unittest.main()
