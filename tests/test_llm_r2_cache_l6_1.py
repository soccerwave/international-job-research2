from __future__ import annotations

import hashlib
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from src.llm.r2_evaluation_cache import R2EvaluationCacheConflict, R2EvaluationCacheStore
from src.state.r2_store import R2StateStore


class FakeS3Error(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeR2Client:
    def __init__(self, *, payload: bytes | None = None, etag: str = '"etag-old"', metadata: dict | None = None):
        self.payload = payload
        self.etag = etag
        self.metadata = metadata or {}
        self.put_calls: list[dict] = []
        self.raise_on_put: Exception | None = None

    def get_object(self, *, Bucket, Key):
        if self.payload is None:
            raise FakeS3Error("NoSuchKey")
        return {
            "Body": BytesIO(self.payload),
            "ETag": self.etag,
            "Metadata": self.metadata,
        }

    def put_object(self, **kwargs):
        if self.raise_on_put is not None:
            raise self.raise_on_put
        self.put_calls.append(kwargs)
        self.payload = bytes(kwargs["Body"])
        self.etag = '"etag-new"'
        self.metadata = dict(kwargs.get("Metadata") or {})
        return {"ETag": self.etag}


class LLMR2DurableCacheTests(unittest.TestCase):
    def _store(self, client: FakeR2Client) -> R2EvaluationCacheStore:
        return R2EvaluationCacheStore(R2StateStore(client, "bucket"))

    def test_missing_remote_cache_hydrates_empty_local_file(self):
        client = FakeR2Client(payload=None)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.jsonl"
            loaded = self._store(client).hydrate(path)
            self.assertFalse(loaded.exists)
            self.assertIsNone(loaded.etag)
            self.assertEqual(path.read_bytes(), b"")

    def test_existing_remote_cache_hydrates_and_verifies_sha(self):
        payload = b'{"cache_fingerprint":"abc","llm_result":{}}\n'
        digest = hashlib.sha256(payload).hexdigest()
        client = FakeR2Client(payload=payload, metadata={"sha256": digest})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.jsonl"
            loaded = self._store(client).hydrate(path)
            self.assertTrue(loaded.exists)
            self.assertEqual(loaded.sha256, digest)
            self.assertEqual(path.read_bytes(), payload)

    def test_integrity_mismatch_is_rejected(self):
        client = FakeR2Client(payload=b"data", metadata={"sha256": "bad"})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                self._store(client).hydrate(Path(tmp) / "cache.jsonl")

    def test_first_sync_uses_if_none_match(self):
        client = FakeR2Client(payload=None)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.jsonl"
            path.write_text("row\n", encoding="utf-8")
            result = self._store(client).sync(path, expected_etag=None)
            self.assertEqual(client.put_calls[0]["custom_headers"], {"If-None-Match": "*"})
            self.assertEqual(result["bytes"], 4)

    def test_existing_sync_uses_if_match(self):
        client = FakeR2Client(payload=b"old\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.jsonl"
            path.write_text("new\n", encoding="utf-8")
            self._store(client).sync(path, expected_etag='"etag-old"')
            self.assertEqual(client.put_calls[0]["custom_headers"], {"If-Match": '"etag-old"'})

    def test_stale_writer_conflict_is_explicit(self):
        client = FakeR2Client(payload=b"old\n")
        client.raise_on_put = FakeS3Error("PreconditionFailed")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.jsonl"
            path.write_text("new\n", encoding="utf-8")
            with self.assertRaises(R2EvaluationCacheConflict):
                self._store(client).sync(path, expected_etag='"etag-old"')


if __name__ == "__main__":
    unittest.main()
