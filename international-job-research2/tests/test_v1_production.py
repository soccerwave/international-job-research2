from __future__ import annotations

import copy
import hashlib
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.runtime.production import (
    PRODUCTION_STATE_KEY,
    assert_production_store,
    strict_production_preflight,
    validate_strict_release_result,
)
from src.runtime.production_shards import production_limit, production_specs, run_production_shard
from src.runtime.recovery import load_backup_state, restore_production_state
from src.state.engine import empty_state, state_bytes


class _BackupClient:
    def __init__(self, backup_key: str, backup_state: dict):
        payload = state_bytes(backup_state)
        self.backup_key = backup_key
        self.payload = payload
        self.sha = hashlib.sha256(payload).hexdigest()

    def get_object(self, *, Bucket, Key):
        if Key != self.backup_key:
            raise KeyError(Key)
        return {"Body": BytesIO(self.payload), "Metadata": {"sha256": self.sha}}


class _FakeRecoveryStore:
    prefix = ""
    current_key = PRODUCTION_STATE_KEY
    bucket = "test-bucket"

    def __init__(self, current_state: dict, backup_key: str, backup_state: dict):
        self.current_state = copy.deepcopy(current_state)
        self.client = _BackupClient(backup_key, backup_state)
        self.etag = '"etag-current"'
        self.publish_calls = []

    def load_current(self, *, allow_missing=True):
        return SimpleNamespace(
            state=copy.deepcopy(self.current_state),
            etag=self.etag,
            exists=True,
            key=self.current_key,
        )

    def publish(self, state, *, expected_etag, run_id):
        self.publish_calls.append((copy.deepcopy(state), expected_etag, run_id))
        if expected_etag != self.etag:
            raise AssertionError("CAS ETag mismatch")
        self.current_state = copy.deepcopy(state)
        self.etag = '"etag-next"'
        return {
            "current_key": self.current_key,
            "backup_key": f"state/backups/g{state['generation']:08d}-{run_id}.json",
            "etag": self.etag,
            "generation": state["generation"],
        }


class V1ProductionTests(unittest.TestCase):
    def test_production_limit_defaults_to_uncapped(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRODUCTION_MAX_JOBS_PER_SOURCE", None)
            self.assertIsNone(production_limit())

    def test_explicit_limit_is_not_clamped(self):
        with patch.dict(os.environ, {"PRODUCTION_MAX_JOBS_PER_SOURCE": "999"}):
            self.assertEqual(production_limit(), 999)
        with patch.dict(os.environ, {"PRODUCTION_MAX_JOBS_PER_SOURCE": "0"}):
            self.assertIsNone(production_limit())

    def test_production_specs_do_not_use_stage10_limit(self):
        with patch.dict(os.environ, {"PRODUCTION_MAX_JOBS_PER_SOURCE": "17", "STAGE10_MAX_JOBS_PER_SOURCE": "5"}):
            with patch("src.runtime.production_shards.production_source_map", return_value={}) as build:
                production_specs()
                build.assert_called_once_with(17)
                self.assertEqual(os.environ["STAGE10_MAX_JOBS_PER_SOURCE"], "5")

    def test_production_shard_marks_bundle_as_production(self):
        spec = SimpleNamespace(source_id="fake", report_key="fake", collector=lambda: [])
        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.runtime.production_shards.production_specs", return_value={"fake-shard": [spec]}), patch(
                "src.runtime.production_shards.write_shard_bundle"
            ) as write_bundle:
                diagnostic = run_production_shard(
                    run_id="prod-test",
                    shard_id="fake-shard",
                    output_root=Path(tmp),
                )
        self.assertEqual(diagnostic.status.value, "PARTIAL")
        self.assertTrue(diagnostic.metadata["production_run"])
        self.assertFalse(diagnostic.errors)
        write_bundle.assert_called_once()

    def test_authoritative_store_rejects_acceptance_prefix(self):
        good = SimpleNamespace(prefix="", current_key=PRODUCTION_STATE_KEY)
        assert_production_store(good)
        bad = SimpleNamespace(prefix="acceptance/stage10/x", current_key="acceptance/stage10/x/state/current/state.json")
        with self.assertRaises(RuntimeError):
            assert_production_store(bad)

    def test_strict_preflight_fails_before_state_when_shard_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = strict_production_preflight(
                run_id="missing",
                artifact_root=Path(tmp),
                observed_at="2026-09-04T21:00:00+00:00",
                expected_shards=["required-shard"],
            )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("missing shard" in item for item in result["failures"]))

    def _strict_result(self):
        return {
            "status": "PASS",
            "missing_shards": [],
            "degraded_sources": [],
            "canonicalization": {"canonical_records": 2},
            "state": {
                "records_observed": 2,
                "NEW": 2,
                "SEEN": 0,
                "MATERIALLY_CHANGED": 0,
                "REOPENED": 0,
                "state_jobs": 2,
            },
            "reporting": {"source_health": {"OK": 4, "PARTIAL": 0, "ERROR": 0, "UNKNOWN": 0}},
            "persistence": {"current_key": PRODUCTION_STATE_KEY},
            "consistency": {
                "state_id_cardinality_matches_canonical": True,
                "absence_inferred_closed": 0,
            },
        }

    def test_strict_release_requires_all_new_on_fresh_bootstrap(self):
        checks = validate_strict_release_result(self._strict_result(), state_before_exists=False)
        self.assertTrue(all(checks.values()))
        bad = self._strict_result()
        bad["state"]["NEW"] = 1
        checks = validate_strict_release_result(bad, state_before_exists=False)
        self.assertFalse(checks["fresh_bootstrap_all_new"])

    def test_strict_release_allows_seen_when_state_already_exists(self):
        result = self._strict_result()
        result["state"].update({"NEW": 0, "SEEN": 2, "state_jobs": 10})
        checks = validate_strict_release_result(result, state_before_exists=True)
        self.assertTrue(all(checks.values()))
        self.assertNotIn("fresh_bootstrap_all_new", checks)

    def test_recovery_rejects_non_backup_key(self):
        state = empty_state()
        store = _FakeRecoveryStore(state, "state/backups/g00000000-x.json", state)
        with self.assertRaises(ValueError):
            load_backup_state(store, "state/current/state.json")

    def test_recovery_restores_as_new_monotonic_generation_with_cas(self):
        backup = empty_state()
        backup["generation"] = 2
        backup["updated_at"] = "2026-09-01T00:00:00+00:00"
        backup["last_run_id"] = "old"
        current = empty_state()
        current["generation"] = 5
        current["updated_at"] = "2026-09-04T20:00:00+00:00"
        current["last_run_id"] = "current"
        key = "state/backups/g00000002-old.json"
        store = _FakeRecoveryStore(current, key, backup)
        result = restore_production_state(
            store=store,
            backup_key=key,
            observed_at="2026-09-04T22:00:00+00:00",
            run_id="manual-restore",
        )
        self.assertEqual(result["previous_generation"], 5)
        self.assertEqual(result["restored_generation"], 6)
        self.assertEqual(store.current_state["generation"], 6)
        self.assertEqual(store.current_state["last_run_id"], "recovery:manual-restore")
        self.assertEqual(store.publish_calls[0][1], '"etag-current"')


if __name__ == "__main__":
    unittest.main()
