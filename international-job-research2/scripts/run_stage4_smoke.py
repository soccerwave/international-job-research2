from pathlib import Path
import shutil
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime.finalizer import finalize_run
from src.runtime.shard_runner import run_shard
from tests.fixtures.stub_collectors import good_collector, second_good_collector, failing_collector


def main() -> int:
    root = REPO_ROOT / ".stage4-smoke"
    if root.exists():
        shutil.rmtree(root)

    run_id = "stage4-smoke"
    run_shard(run_id=run_id, shard_id="alpha", source_ids=["stub-alpha"], collector=good_collector, output_root=root)
    run_shard(run_id=run_id, shard_id="beta", source_ids=["stub-beta"], collector=second_good_collector, output_root=root)
    run_shard(run_id=run_id, shard_id="broken", source_ids=["stub-broken"], collector=failing_collector, output_root=root)
    summary = finalize_run(run_id=run_id, artifact_root=root, output_root=root)

    assert summary.status.value == "PARTIAL"
    assert summary.shards_accepted == 2
    assert summary.shards_rejected == 1
    assert summary.records_loaded == 2
    print(summary.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
