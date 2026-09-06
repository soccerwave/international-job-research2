from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.runtime.artifacts import write_shard_bundle
from src.runtime.contracts import ShardDiagnostic, ShardStatus
from src.runtime.preprod import run_preprod_finalization
from tests.test_stage10_preprod import _job, _full_detail


class Stage10MissingShardTests(unittest.TestCase):
    def test_missing_expected_shard_is_partial_and_never_infers_closure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_id = "stage10-missing-shard"
            state_path = root / "state.json"
            record = _job("1", source_key="healthy", detail=_full_detail())
            diag = ShardDiagnostic(
                shard_id="healthy-shard",
                source_ids=["healthy"],
                status=ShardStatus.OK,
                started_at="2026-09-04T20:00:00+00:00",
                finished_at="2026-09-04T20:00:01+00:00",
                elapsed_ms=1000,
                records_observed=1,
                records_emitted=1,
            )
            write_shard_bundle(
                root=root,
                run_id=run_id,
                shard_id="healthy-shard",
                source_ids=["healthy"],
                records=[record],
                diagnostic=diag,
                producer_version="stage10-test",
            )

            result = run_preprod_finalization(
                run_id=run_id,
                artifact_root=root,
                output_root=root,
                observed_at="2026-09-04T20:00:00+00:00",
                state_backend="LOCAL",
                state_path=state_path,
                expected_shards=["healthy-shard", "missing-shard"],
            )

            self.assertEqual(result["status"], "PARTIAL_PASS")
            self.assertEqual(result["missing_shards"], ["missing-shard"])
            self.assertEqual(result["source_diagnostics"]["shard::missing-shard"]["error"], "MISSING_SHARD_ARTIFACT")
            self.assertEqual(result["state"]["not_observed_inferred_closed"], 0)
            self.assertTrue(result["consistency"]["missing_shards_surface_as_partial"])


if __name__ == "__main__":
    unittest.main()
