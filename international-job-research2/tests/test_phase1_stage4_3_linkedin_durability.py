import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.sources.shared import linkedin_mads as li


class LinkedInDurabilityTests(unittest.TestCase):
    def collect(self, runner, checkpoint_dir, **kwargs):
        with patch.object(li, "resolve_repo", return_value=Path("/tmp")), patch.dict(
            os.environ, {"LINKEDIN_CHECKPOINT_DIR": str(checkpoint_dir)}, clear=False
        ):
            return li.collect(
                locations=("Ireland",),
                queries=("research fellow",),
                limit_per_search=None,
                max_jobs=None,
                runner=runner,
                **kwargs,
            )

    def test_completed_discovery_page_survives_interrupt_on_next_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)

            def runner(repo, args):
                if args[1] == "detail":
                    raise AssertionError("detail must not start")
                page=int(args[args.index("--page") + 1])
                if page == 1:
                    payload={"results":[{"id":"101","title":"Research Fellow","company":"Example University"}]}
                    return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
                raise KeyboardInterrupt()

            with self.assertRaises(KeyboardInterrupt):
                self.collect(runner, root, enrich_detail=False)

            discovery=root/"discovery.jsonl"
            self.assertTrue(discovery.exists())
            events=[json.loads(line) for line in discovery.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["page"], 1)
            self.assertEqual(events[0]["country"], "Ireland")
            self.assertEqual(events[0]["query"], "research fellow")
            self.assertEqual(events[0]["items"][0]["id"], "101")
            state=json.loads((root/"state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["stage"], "discovery")
            self.assertEqual(state["completed_pages"], 1)

    def test_completed_record_survives_interrupt_during_later_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            detail_calls=0

            def runner(repo, args):
                nonlocal detail_calls
                if args[1] == "detail":
                    detail_calls += 1
                    if detail_calls == 1:
                        return SimpleNamespace(returncode=0, stdout="FULL JD " * 40, stderr="")
                    raise KeyboardInterrupt()
                page=int(args[args.index("--page") + 1])
                results=(
                    [
                        {"id":"201","title":"Research Fellow A","company":"Example University"},
                        {"id":"202","title":"Research Fellow B","company":"Example University"},
                    ]
                    if page == 1 else []
                )
                return SimpleNamespace(returncode=0, stdout=json.dumps({"results":results}), stderr="")

            with self.assertRaises(KeyboardInterrupt):
                self.collect(runner, root, enrich_detail=True)

            records=root/"records.jsonl"
            self.assertTrue(records.exists())
            rows=[json.loads(line) for line in records.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            record=rows[0]["record"]
            self.assertEqual(record["source"]["source_job_id"], "201")
            self.assertIn("FULL JD", record["description"]["full_jd"])
            state=json.loads((root/"state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["stage"], "detail")
            self.assertEqual(state["completed_records"], 1)
            self.assertEqual(state["last_job_id"], "201")

    def test_successful_run_marks_checkpoint_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)

            def runner(repo, args):
                if args[1] == "detail":
                    return SimpleNamespace(returncode=0, stdout="FULL JD " * 40, stderr="")
                page=int(args[args.index("--page") + 1])
                results=[{"id":"301","title":"Research Fellow","company":"Example University"}] if page == 1 else []
                return SimpleNamespace(returncode=0, stdout=json.dumps({"results":results}), stderr="")

            rows=self.collect(runner, root, enrich_detail=True)
            self.assertEqual(len(rows), 1)
            state=json.loads((root/"state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "COMPLETE")
            self.assertEqual(state["stage"], "complete")
            self.assertEqual(state["completed_records"], 1)
            self.assertEqual(state["total_records"], 1)

    def test_checkpointing_does_not_change_collector_output(self):
        def runner(repo, args):
            if args[1] == "detail":
                return SimpleNamespace(returncode=0, stdout="FULL JD " * 40, stderr="")
            page=int(args[args.index("--page") + 1])
            results=[{"id":"401","title":"Research Fellow","company":"Example University"}] if page == 1 else []
            return SimpleNamespace(returncode=0, stdout=json.dumps({"results":results}), stderr="")

        with patch.object(li, "resolve_repo", return_value=Path("/tmp")), patch.dict(
            os.environ, {}, clear=False
        ):
            os.environ.pop("LINKEDIN_CHECKPOINT_DIR", None)
            rows=li.collect(
                locations=("Ireland",),queries=("research fellow",),
                limit_per_search=None,max_jobs=None,runner=runner,enrich_detail=True,
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"]["source_job_id"], "401")


if __name__ == "__main__":
    unittest.main()
