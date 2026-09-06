from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from .engine import empty_state, state_bytes, state_sha256, validate_state

CURRENT_STATE_KEY = "state/current/state.json"


class StateConflict(RuntimeError):
    """Raised when optimistic concurrency detects a stale state writer."""


@dataclass(frozen=True)
class LoadedState:
    state: dict[str, Any]
    etag: str | None
    exists: bool
    key: str


def _required_env(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


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
    raise RuntimeError("R2 GetObject returned an unsupported body type")


def _configure_conditional_headers(client: Any) -> None:
    """Enable per-request custom headers exactly as documented for Cloudflare R2+boto3."""
    events = getattr(getattr(client, "meta", None), "events", None)
    if events is None:
        return

    def process_custom_arguments(params, context, **kwargs):
        custom = params.pop("custom_headers", None)
        if custom:
            context["custom_headers"] = custom

    def add_custom_headers(params, context, **kwargs):
        custom = context.get("custom_headers")
        if custom:
            params["headers"].update(custom)

    events.register("before-parameter-build.s3.PutObject", process_custom_arguments)
    events.register("before-call.s3.PutObject", add_custom_headers)


class R2StateStore:
    def __init__(self, client: Any, bucket: str, prefix: str = "") -> None:
        self.client = client
        self.bucket = str(bucket).strip()
        if not self.bucket:
            raise ValueError("R2 bucket is required")
        self.prefix = str(prefix or "").strip("/")

    @classmethod
    def from_env(cls, *, prefix: str | None = None) -> "R2StateStore":
        import boto3

        account_id = _required_env("R2_ACCOUNT_ID")
        endpoint = str(os.environ.get("R2_ENDPOINT") or f"https://{account_id}.r2.cloudflarestorage.com").strip()
        client = boto3.client(
            service_name="s3",
            endpoint_url=endpoint,
            aws_access_key_id=_required_env("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=_required_env("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )
        _configure_conditional_headers(client)
        chosen_prefix = str(prefix if prefix is not None else os.environ.get("R2_STATE_PREFIX") or "").strip("/")
        return cls(client, _required_env("R2_BUCKET"), chosen_prefix)

    def key(self, relative: str) -> str:
        relative = relative.strip("/")
        return f"{self.prefix}/{relative}" if self.prefix else relative

    @property
    def current_key(self) -> str:
        return self.key(CURRENT_STATE_KEY)

    def _put(self, *, key: str, payload: bytes, headers: dict[str, str], metadata: dict[str, str]) -> dict[str, Any]:
        kwargs = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": payload,
            "ContentType": "application/json",
            "Metadata": metadata,
        }
        if headers:
            kwargs["custom_headers"] = headers
        try:
            return self.client.put_object(**kwargs)
        except Exception as exc:
            if _precondition_failed(exc):
                raise StateConflict(f"R2 conditional write rejected for {key}: stale or duplicate writer") from exc
            raise

    def load_current(self, *, allow_missing: bool = True) -> LoadedState:
        key = self.current_key
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _not_found(exc) and allow_missing:
                return LoadedState(empty_state(), None, False, key)
            raise
        raw = _body_bytes(response.get("Body"))
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"R2 state object is corrupt JSON: {key}") from exc
        validate_state(data)
        metadata = response.get("Metadata") or {}
        expected_sha = str(metadata.get("sha256") or "").strip()
        actual_sha = hashlib.sha256(raw).hexdigest()
        if expected_sha and expected_sha != actual_sha:
            raise RuntimeError(f"R2 state integrity mismatch for {key}")
        return LoadedState(data, _clean_etag(response.get("ETag")), True, key)

    def bootstrap(self, state: dict[str, Any], *, run_id: str) -> dict[str, Any]:
        validate_state(state)
        payload = state_bytes(state)
        digest = hashlib.sha256(payload).hexdigest()
        safe_run = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id).strip("_") or "bootstrap"
        backup = self.key(f"state/bootstrap/g{int(state['generation']):08d}-{safe_run}.json")
        metadata = {"sha256": digest, "state-version": str(state["state_version"]), "generation": str(state["generation"])}
        self._put(key=backup, payload=payload, headers={"If-None-Match": "*"}, metadata=metadata)
        current = self._put(key=self.current_key, payload=payload, headers={"If-None-Match": "*"}, metadata=metadata)
        verified = self.load_current(allow_missing=False)
        if state_sha256(verified.state) != state_sha256(state):
            raise RuntimeError("R2 bootstrap verification failed")
        return {"current_key": self.current_key, "backup_key": backup, "etag": _clean_etag(current.get("ETag")), "sha256": digest}

    def publish(self, state: dict[str, Any], *, expected_etag: str | None, run_id: str) -> dict[str, Any]:
        """Publish one new generation using compare-and-swap on state/current."""
        validate_state(state)
        payload = state_bytes(state)
        digest = hashlib.sha256(payload).hexdigest()
        generation = int(state["generation"])
        safe_run = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id).strip("_") or f"g{generation}"
        backup = self.key(f"state/backups/g{generation:08d}-{safe_run}.json")
        metadata = {"sha256": digest, "state-version": str(state["state_version"]), "generation": str(generation)}

        # Immutable backup first. If the current CAS later fails, the orphaned backup is
        # useful audit evidence and never becomes authoritative state.
        self._put(key=backup, payload=payload, headers={"If-None-Match": "*"}, metadata=metadata)
        headers = {"If-Match": expected_etag} if expected_etag else {"If-None-Match": "*"}
        current = self._put(key=self.current_key, payload=payload, headers=headers, metadata=metadata)

        verified = self.load_current(allow_missing=False)
        if state_sha256(verified.state) != state_sha256(state):
            raise RuntimeError("R2 post-write verification failed")
        return {
            "current_key": self.current_key,
            "backup_key": backup,
            "previous_etag": expected_etag,
            "etag": _clean_etag(current.get("ETag")) or verified.etag,
            "generation": generation,
            "sha256": digest,
        }
