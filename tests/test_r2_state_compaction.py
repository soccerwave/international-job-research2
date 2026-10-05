from __future__ import annotations

import copy
import json
import unittest

from src.state.r2_store import compact_state_bytes, state_for_storage


class R2StateCompactionTests(unittest.TestCase):
    def _state(self):
        return {
            "state_version": "STATE_SCHEMA_V1.0.0",
            "generation": 7,
            "updated_at": "2026-10-05T00:00:00Z",
            "last_run_id": "test",
            "writer_role": "CENTRAL_FINALIZER",
            "jobs": {
                "job_abc": {
                    "state_id": "job_abc",
                    "aliases": ["canonical:abc"],
                    "last_snapshot": {
                        "title": "research fellow",
                        "recommendation": "APPLY",
                        "evaluation_dimensions": {
                            "domain_fit": "HIGH",
                            "role_fit": "HIGH",
                            "evidence": ["example"],
                        },
                    },
                }
            },
        }

    def test_storage_copy_removes_only_evaluation_dimensions(self):
        original = self._state()
        before = copy.deepcopy(original)
        durable = state_for_storage(original)
        self.assertNotIn("evaluation_dimensions", durable["jobs"]["job_abc"]["last_snapshot"])
        self.assertEqual(durable["jobs"]["job_abc"]["last_snapshot"]["recommendation"], "APPLY")
        self.assertEqual(original, before)

    def test_compact_payload_roundtrip_has_no_dimensions(self):
        original = self._state()
        payload = compact_state_bytes(original)
        parsed = json.loads(payload.decode("utf-8"))
        self.assertNotIn("evaluation_dimensions", parsed["jobs"]["job_abc"]["last_snapshot"])
        self.assertEqual(parsed["jobs"]["job_abc"]["last_snapshot"]["title"], "research fellow")

    def test_compaction_is_idempotent(self):
        durable = state_for_storage(self._state())
        self.assertEqual(state_for_storage(durable), durable)


if __name__ == "__main__":
    unittest.main()
