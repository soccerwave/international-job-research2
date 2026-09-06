import tempfile
import unittest
from pathlib import Path

from src.runtime.state_writer import FinalizerStateWriter
from src.state.engine import load_state
from src.state.r2_store import R2StateStore
from tests.test_stage8_r2 import FakeR2Client
from tests.test_stage8_state import job


class Stage8FinalizerStateWriterTests(unittest.TestCase):
    def test_local_writer_persists_new_then_seen(self):
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            first = FinalizerStateWriter.persist_local(
                [job()],
                state_path=state_path,
                observed_at="2026-09-04T12:00:00Z",
                run_id="local-1",
            )
            self.assertEqual(first.summary["NEW"], 1)
            self.assertEqual(first.persistence["backend"], "LOCAL_ATOMIC_FILE")
            second = FinalizerStateWriter.persist_local(
                [job()],
                state_path=state_path,
                observed_at="2026-09-05T12:00:00Z",
                run_id="local-2",
            )
            self.assertEqual(second.summary["SEEN"], 1)
            state = load_state(state_path)
            self.assertEqual(state["generation"], 2)
            self.assertEqual(state["last_run_id"], "local-2")

    def test_r2_writer_requires_explicit_bootstrap(self):
        store = R2StateStore(FakeR2Client(), "bucket")
        with self.assertRaises(RuntimeError):
            FinalizerStateWriter.persist_r2(
                [job()],
                store=store,
                observed_at="2026-09-04T12:00:00Z",
                run_id="r2-1",
                allow_bootstrap=False,
            )

    def test_r2_writer_can_explicitly_bootstrap_then_publish(self):
        store = R2StateStore(FakeR2Client(), "bucket")
        result = FinalizerStateWriter.persist_r2(
            [job()],
            store=store,
            observed_at="2026-09-04T12:00:00Z",
            run_id="r2-1",
            allow_bootstrap=True,
        )
        self.assertEqual(result.summary["NEW"], 1)
        self.assertEqual(result.persistence["backend"], "CLOUDFLARE_R2_CAS")
        self.assertEqual(result.persistence["generation"], 1)
        loaded = store.load_current(allow_missing=False)
        self.assertEqual(loaded.state["generation"], 1)
        self.assertEqual(loaded.state["last_run_id"], "r2-1")

    def test_writer_preserves_absent_history(self):
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            FinalizerStateWriter.persist_local(
                [job("1"), job("2")],
                state_path=state_path,
                observed_at="2026-09-04T12:00:00Z",
                run_id="local-1",
            )
            FinalizerStateWriter.persist_local(
                [job("1")],
                state_path=state_path,
                observed_at="2026-09-05T12:00:00Z",
                run_id="local-2",
            )
            state = load_state(state_path)
            self.assertEqual(len(state["jobs"]), 2)
            second = [e for e in state["jobs"].values() if "source_id:fixture:2" in e["aliases"]][0]
            self.assertEqual(second["lifecycle_status"], "OPEN")
            self.assertEqual(second["last_seen_at"], "2026-09-04T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
