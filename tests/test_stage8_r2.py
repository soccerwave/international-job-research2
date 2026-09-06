import hashlib
import io
import unittest

from src.state.engine import WRITER_ROLE, apply_state, empty_state, state_bytes
from src.state.r2_store import R2StateStore, StateConflict


class FakeClientError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class FakeR2Client:
    def __init__(self):
        self.objects = {}
        self.put_log = []

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        body = bytes(kwargs["Body"])
        headers = kwargs.get("custom_headers") or {}
        current = self.objects.get(key)
        if headers.get("If-None-Match") == "*" and current is not None:
            raise FakeClientError("PreconditionFailed")
        if "If-Match" in headers:
            if current is None or current["etag"] != headers["If-Match"]:
                raise FakeClientError("PreconditionFailed")
        etag = '"' + hashlib.md5(body).hexdigest() + '"'
        self.objects[key] = {"body": body, "etag": etag, "metadata": dict(kwargs.get("Metadata") or {})}
        self.put_log.append((key, dict(headers)))
        return {"ETag": etag}

    def get_object(self, **kwargs):
        key = kwargs["Key"]
        if key not in self.objects:
            raise FakeClientError("NoSuchKey")
        obj = self.objects[key]
        return {"Body": io.BytesIO(obj["body"]), "ETag": obj["etag"], "Metadata": dict(obj["metadata"])}


def next_state(state, run_id="r1"):
    record = {
        "schema_version": "VACANCY_SCHEMA_V1.0.0",
        "record_stage": "SHARD_ENRICHED",
        "source_record_id": "fixture:1",
        "canonical_id": None,
        "source": {"source_key":"fixture","source_job_id":"1","listing_url":"https://example.org/jobs/1","detail_url":"https://example.org/jobs/1","apply_url":None,"source_status":"OPEN"},
        "position": {"title_raw":"Postdoc in Exercise","institution_raw":"Example University","department":None,"role_family":"POSTDOC","role_level":"POSTDOC","employment_type":"FULL_TIME","workplace_mode":"ONSITE"},
        "location": {"country_code":"NL","city":"Amsterdam"},
        "dates": {"deadline_at":None,"deadline_status":"UNKNOWN"},
        "contract": {"term_type":"FIXED_TERM","duration_months":24,"fte":1.0},
        "description": {"full_jd":"exercise physiology physical activity fitness intervention research " * 8,"detail_status":"FULL"},
        "raw_extra": {},
    }
    new_state, _ = apply_state([record], state, observed_at="2026-09-04T12:00:00Z", run_id=run_id, writer_role=WRITER_ROLE)
    return new_state


class Stage8R2Tests(unittest.TestCase):
    def setUp(self):
        self.client = FakeR2Client()
        self.store = R2StateStore(self.client, "test-bucket")

    def test_missing_current_returns_empty_state(self):
        loaded = self.store.load_current()
        self.assertFalse(loaded.exists)
        self.assertIsNone(loaded.etag)
        self.assertEqual(loaded.state["generation"], 0)

    def test_bootstrap_uses_create_only_and_verifies(self):
        result = self.store.bootstrap(empty_state(), run_id="bootstrap-1")
        self.assertIn("state/current/state.json", self.client.objects)
        self.assertEqual(self.client.put_log[-1][1], {"If-None-Match": "*"})
        loaded = self.store.load_current(allow_missing=False)
        self.assertTrue(loaded.exists)
        self.assertEqual(result["sha256"], hashlib.sha256(state_bytes(loaded.state)).hexdigest())

    def test_duplicate_bootstrap_conflicts(self):
        self.store.bootstrap(empty_state(), run_id="bootstrap-1")
        with self.assertRaises(StateConflict):
            self.store.bootstrap(empty_state(), run_id="bootstrap-2")

    def test_publish_uses_expected_etag_compare_and_swap(self):
        self.store.bootstrap(empty_state(), run_id="bootstrap")
        loaded = self.store.load_current(allow_missing=False)
        state1 = next_state(loaded.state)
        result = self.store.publish(state1, expected_etag=loaded.etag, run_id="run-1")
        self.assertEqual(result["generation"], 1)
        self.assertEqual(self.client.put_log[-1][1], {"If-Match": loaded.etag})
        self.assertEqual(self.store.load_current(allow_missing=False).state["generation"], 1)

    def test_stale_writer_cannot_overwrite_newer_state(self):
        self.store.bootstrap(empty_state(), run_id="bootstrap")
        stale = self.store.load_current(allow_missing=False)
        state1 = next_state(stale.state, "run-1")
        self.store.publish(state1, expected_etag=stale.etag, run_id="run-1")
        stale_candidate = next_state(stale.state, "run-stale")
        with self.assertRaises(StateConflict):
            self.store.publish(stale_candidate, expected_etag=stale.etag, run_id="run-stale")
        self.assertEqual(self.store.load_current(allow_missing=False).state["last_run_id"], "run-1")

    def test_backup_is_immutable(self):
        self.store.bootstrap(empty_state(), run_id="bootstrap")
        loaded = self.store.load_current(allow_missing=False)
        state1 = next_state(loaded.state)
        self.store.publish(state1, expected_etag=loaded.etag, run_id="same-run")
        current = self.store.load_current(allow_missing=False)
        state2 = next_state(current.state, "r2")
        # Forcing the same backup generation/run key must be rejected before overwrite.
        state2["generation"] = state1["generation"]
        with self.assertRaises(StateConflict):
            self.store.publish(state2, expected_etag=current.etag, run_id="same-run")

    def test_integrity_metadata_mismatch_is_rejected(self):
        self.store.bootstrap(empty_state(), run_id="bootstrap")
        obj = self.client.objects["state/current/state.json"]
        obj["metadata"]["sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            self.store.load_current(allow_missing=False)

    def test_prefix_isolation(self):
        isolated = R2StateStore(self.client, "test-bucket", "acceptance/run-42")
        isolated.bootstrap(empty_state(), run_id="bootstrap")
        self.assertIn("acceptance/run-42/state/current/state.json", self.client.objects)
        self.assertNotIn("state/current/state.json", self.client.objects)


if __name__ == "__main__":
    unittest.main()
