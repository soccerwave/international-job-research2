from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src.runtime.live_shards import SourceCall
from src.runtime import production_shards


class Stage52StallDiagnosticsTests(unittest.TestCase):
    def _events(self, path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_source_operation_emits_start_heartbeat_and_collector_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            progress = Path(tmp) / "source_lifecycle.jsonl"
            with patch.dict(os.environ, {"PRODUCTION_PROGRESS_PATH": str(progress)}), \
                 patch.object(production_shards, "PRODUCTION_HEARTBEAT_SECONDS", 0.01):
                with production_shards._source_operation(
                    run_id="run-1",
                    shard_id="linkedin-europe-germany",
                    source_id="linkedin_europe",
                    report_key="linkedin_mads",
                ):
                    time.sleep(0.035)

            events = self._events(progress)
            names = [event["event"] for event in events]
            self.assertEqual(names[0], "source_start")
            self.assertIn("source_waiting", names)
            self.assertEqual(names[-1], "source_collector_done")
            waiting = next(event for event in events if event["event"] == "source_waiting")
            self.assertEqual(waiting["shard_id"], "linkedin-europe-germany")
            self.assertEqual(waiting["source_id"], "linkedin_europe")
            self.assertGreaterEqual(waiting["elapsed_seconds"], 0)

    def test_source_operation_emits_error_before_reraising(self):
        with tempfile.TemporaryDirectory() as tmp:
            progress = Path(tmp) / "source_lifecycle.jsonl"
            with patch.dict(os.environ, {"PRODUCTION_PROGRESS_PATH": str(progress)}):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    with production_shards._source_operation(
                        run_id="run-2",
                        shard_id="thematic",
                        source_id="ecss",
                        report_key="ecss",
                    ):
                        raise RuntimeError("boom")

            events = self._events(progress)
            self.assertEqual([event["event"] for event in events], ["source_start", "source_error"])
            self.assertEqual(events[-1]["error_type"], "RuntimeError")
            self.assertEqual(events[-1]["error"], "boom")

    def test_run_production_shard_emits_terminal_source_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "source_lifecycle.jsonl"
            spec = SourceCall("fake_source", "fake_report", lambda: [])
            with patch.dict(os.environ, {"PRODUCTION_PROGRESS_PATH": str(progress)}), \
                 patch.object(production_shards, "production_specs", return_value={"fake-shard": [spec]}):
                diagnostic = production_shards.run_production_shard(
                    run_id="run-3",
                    shard_id="fake-shard",
                    output_root=root,
                )

            events = self._events(progress)
            terminal = [event for event in events if event["event"] == "source_done"]
            self.assertEqual(len(terminal), 1)
            self.assertEqual(terminal[0]["source_id"], "fake_source")
            self.assertEqual(terminal[0]["status"], "PARTIAL")
            self.assertEqual(diagnostic.metadata["source_results"][0]["status"], "PARTIAL")


if __name__ == "__main__":
    unittest.main()
