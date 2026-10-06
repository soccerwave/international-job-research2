from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.state.r2_store import R2StateStore

DEFAULT_R2_CACHE_KEY = "llm/cache/evaluations-v0.1.jsonl"


class R2EvaluationCacheConflict(RuntimeError):
    """Raised when another writer changed the durable cache after hydration."""


@dataclass(frozen=True)
class LoadedR2EvaluationCache:
    key: str
    etag: str | None
    exists: bool
    sha256: str | None
    bytes_loaded: int


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error") or {}
        return str(error.get("Code") or response.get("ResponseMetadata", {}).get("HTTPStatusCode") or "")
    return ""


def _not_found(exc: Exception) -> bool:
    return _error_code(exc) in {"404", "NoSuchKey", "NotFound", "NoSuchObject"}


def _precondition_failed(exc: Exception) -> bool:
    return _error_code(exc) in {"412", "PreconditionFailed", "ConditionalRequestConflict"}


def _clean_etag(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _body_bytes(body: Any) -> bytes:
    value = body.read() if hasattr(body, "read") else body
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    raise RuntimeError("R2 cache GetObject returned an unsupported body type")


class R2EvaluationCacheStore:
    """Durable storage for the successful-evaluation JSONL cache.

    This deliberately uses a separate R2 object from authoritative job state.
    Hydration is one GET per run and sync is one conditional PUT per run.
    """

    def __init__(self, state_store: R2StateStore, *, relative_key: str = DEFAULT_R2_CACHE_KEY) -> None:
        self.state_store = state_store
        self.relative_key = str(relative_key or "").strip("/")
        if not self.relative_key:
            raise ValueError("R2 LLM cache key is required")

    @classmethod
    def from_env(cls) -> "R2EvaluationCacheStore":
        relative_key = str(os.getenv("LLM_R2_CACHE_KEY") or DEFAULT_R2_CACHE_KEY).strip("/")
        return cls(R2StateStore.from_env(), relative_key=relative_key)

    @property
    def key(self) -> str:
        return self.state_store.key(self.relative_key)

    def hydrate(self, local_path: Path) -> LoadedR2EvaluationCache:
        try:
            response = self.state_store.client.get_object(Bucket=self.state_store.bucket, Key=self.key)
        except Exception as exc:
            if _not_found(exc):
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_text("", encoding="utf-8")
                return LoadedR2EvaluationCache(self.key, None, False, None, 0)
            raise

        raw = _body_bytes(response.get("Body"))
        metadata = response.get("Metadata") or {}
        expected_sha = str(metadata.get("sha256") or "").strip()
        actual_sha = hashlib.sha256(raw).hexdigest()
        if expected_sha and expected_sha != actual_sha:
            raise RuntimeError(f"R2 LLM cache integrity mismatch for {self.key}")

        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(raw)
        return LoadedR2EvaluationCache(
            self.key,
            _clean_etag(response.get("ETag")),
            True,
            actual_sha,
            len(raw),
        )

    def sync(self, local_path: Path, *, expected_etag: str | None) -> dict[str, Any]:
        payload = local_path.read_bytes() if local_path.exists() else b""
        digest = hashlib.sha256(payload).hexdigest()
        headers = {"If-Match": expected_etag} if expected_etag else {"If-None-Match": "*"}
        kwargs = {
            "Bucket": self.state_store.bucket,
            "Key": self.key,
            "Body": payload,
            "ContentType": "application/x-ndjson",
            "Metadata": {
                "sha256": digest,
                "cache-version": "LLM_EVALUATION_CACHE_V0.1",
            },
            "custom_headers": headers,
        }
        try:
            response = self.state_store.client.put_object(**kwargs)
        except Exception as exc:
            if _precondition_failed(exc):
                raise R2EvaluationCacheConflict(
                    f"R2 LLM cache changed after hydration; refusing stale overwrite for {self.key}"
                ) from exc
            raise
        return {
            "key": self.key,
            "etag": _clean_etag(response.get("ETag")),
            "sha256": digest,
            "bytes": len(payload),
        }
