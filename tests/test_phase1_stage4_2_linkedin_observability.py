import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.sources.shared import linkedin_mads as li
from src.sources.shared.pagination import capture_coverage


class LinkedInObservabilityTests(unittest.TestCase):
    def collect(self, runner, **kwargs):
        with patch.object(li, "resolve_repo", return_value=Path("/tmp")):
            return li.collect(
                locations=("Ireland",),
                queries=("research fellow",),
                limit_per_search=None,
                max_jobs=None,
                runner=runner,
                **kwargs,
            )

    def scenario(self, failure=None, enrich=True):
        events=[]

        def runner(repo, args):
            if args[1] == "detail":
                if failure == "detail":
                    raise subprocess.TimeoutExpired("bun", 180)
                return SimpleNamespace(returncode=0, stdout="PRIVATE_JD_TEXT " * 30, stderr="")
            page=int(args[args.index("--page") + 1])
            if failure == "search" and page == 2:
                return SimpleNamespace(returncode=1, stdout="", stderr="Request failed: 429 Too Many Requests")
            results=[{"id":"123456","title":"Research Fellow"}] if page == 1 else []
            return SimpleNamespace(returncode=0, stdout=json.dumps({"results":results}), stderr="")

        with patch.object(li, "_progress", side_effect=lambda event, **kw: events.append(dict(event=event, **kw))), capture_coverage() as coverage:
            rows=self.collect(runner, enrich_detail=enrich)
        return rows, events, coverage

    def test_search_failure_reports_exact_country_query_and_page(self):
        rows, events, coverage=self.scenario("search", False)
        self.assertEqual(len(rows), 1)
        error=next(e for e in events if e["event"] == "request_error")
        self.assertEqual((error["stage"], error["country"], error["query"], error["page"]),
                         ("search", "Ireland", "research fellow", 2))
        self.assertIn("429", error["error"])
        self.assertFalse(coverage[-1]["complete"])
        self.assertEqual(coverage[-1]["stop_reason"], "request_failed")

    def test_detail_timeout_reports_job_and_position_without_dropping_listing(self):
        rows, events, _=self.scenario("detail")
        self.assertEqual(len(rows), 1)
        error=next(e for e in events if e["event"] == "request_error")
        self.assertEqual(error["error_type"], "TimeoutExpired")
        self.assertEqual((error["job_id"], error["index"], error["total"]), ("123456", 1, 1))
        self.assertEqual(events[-1]["detail_failures"], 1)

    def test_heartbeat_is_emitted_while_request_is_waiting(self):
        pulse=threading.Event(); events=[]

        def log(event, **kw):
            events.append(event)
            if event == "request_waiting":
                pulse.set()

        with patch.object(li, "HEARTBEAT_SECONDS", 0.01), patch.object(li, "_progress", side_effect=log):
            with li._operation("detail", job_id="123456", index=1, total=1):
                self.assertTrue(pulse.wait(1))
        self.assertIn("request_waiting", events)
        self.assertEqual(events[-1], "request_done")

    def test_progress_jsonl_is_written_before_operation_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory) / "diagnostics" / "progress.jsonl"
            with patch.dict(os.environ, {"LINKEDIN_PROGRESS_PATH":str(path)}), redirect_stderr(io.StringIO()):
                with self.assertRaises(KeyboardInterrupt):
                    with li._operation("search", country="Ireland", query="research fellow", page=1):
                        first=json.loads(path.read_text(encoding="utf-8").splitlines()[0])
                        self.assertEqual(first["event"], "request_start")
                        raise KeyboardInterrupt()
            self.assertTrue(path.exists())

    def test_collection_summary_separates_discovery_and_detail_and_never_logs_jd(self):
        rows, events, _=self.scenario()
        self.assertEqual(len(rows), 1)
        summary=events[-1]
        self.assertEqual(summary["event"], "collection_done")
        self.assertEqual(summary["detail_failures"], 0)
        self.assertIn("discovery_seconds", summary)
        self.assertIn("detail_seconds", summary)
        self.assertNotIn("PRIVATE_JD_TEXT", json.dumps(events))


if __name__ == "__main__":
    unittest.main()
