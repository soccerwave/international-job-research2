import json
import tempfile
import unittest
from pathlib import Path

from src.runtime.artifacts import verify_shard_bundle
from src.runtime.finalizer import finalize_run
from src.runtime.shard_runner import run_shard
from src.runtime.contracts import FinalizerStatus, ShardStatus
from tests.fixtures.stub_collectors import good_collector, second_good_collector, failing_collector


class Stage4RuntimeTests(unittest.TestCase):
    def test_successful_shard_bundle_is_immutable_and_verifiable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rc = run_shard(
                run_id="run-1",
                shard_id="shard-a",
                source_ids=["stub_source"],
                collector=good_collector,
                output_root=root,
                producer_version="V0.4_SHARDED_RUNTIME",
            )
            self.assertEqual(rc, 0)
            manifest, records, diagnostics = verify_shard_bundle(root / "run-1" / "shards" / "shard-a")
            self.assertEqual(manifest.status, ShardStatus.OK)
            self.assertEqual(len(records), 1)
            self.assertEqual(diagnostics["status"], "OK")

            with self.assertRaises(FileExistsError):
                run_shard(
                    run_id="run-1",
                    shard_id="shard-a",
                    source_ids=["stub_source"],
                    collector=good_collector,
                    output_root=root,
                )

    def test_checksum_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_shard(run_id="run-corrupt", shard_id="a", source_ids=["a"], collector=good_collector, output_root=root)
            records_path = root / "run-corrupt" / "shards" / "a" / "records.json"
            records_path.write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                verify_shard_bundle(root / "run-corrupt" / "shards" / "a")

    def test_failed_shard_does_not_prevent_successful_shard_fanin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_shard(run_id="run-2", shard_id="good", source_ids=["a"], collector=good_collector, output_root=root)
            run_shard(run_id="run-2", shard_id="bad", source_ids=["b"], collector=failing_collector, output_root=root)
            summary = finalize_run(run_id="run-2", artifact_root=root, output_root=root)
            self.assertEqual(summary.status, FinalizerStatus.PARTIAL)
            self.assertEqual(summary.shards_accepted, 1)
            self.assertEqual(summary.shards_rejected, 1)
            final_records = json.loads((root / "run-2" / "finalizer" / "records.json").read_text())
            self.assertEqual(len(final_records), 1)

    def test_fanin_combines_independent_successful_shards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_shard(run_id="run-3", shard_id="a", source_ids=["a"], collector=good_collector, output_root=root)
            run_shard(run_id="run-3", shard_id="b", source_ids=["b"], collector=second_good_collector, output_root=root)
            summary = finalize_run(run_id="run-3", artifact_root=root, output_root=root)
            self.assertEqual(summary.status, FinalizerStatus.OK)
            self.assertEqual(summary.shards_accepted, 2)
            self.assertEqual(summary.records_loaded, 2)


if __name__ == "__main__":
    unittest.main()
