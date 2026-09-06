from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .contracts import ShardDiagnostic, ShardManifest, ShardStatus, utc_now_iso

CONTRACT_VERSION = "SHARD_ARTIFACT_CONTRACT_V1.0.0"


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_create_bytes(path: Path, data: bytes) -> None:
    """Publish one immutable file with atomic no-clobber semantics.

    A temporary file is fully written and fsynced first. The final publish uses
    an atomic hard-link creation, which fails with FileExistsError if another
    process has already published the same immutable artifact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp_name, path)
        except FileExistsError as exc:
            raise FileExistsError(f"immutable artifact already exists: {path}") from exc
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_shard_bundle(
    *,
    root: Path,
    run_id: str,
    shard_id: str,
    source_ids: list[str],
    records: Iterable[dict[str, Any]],
    diagnostic: ShardDiagnostic,
    producer_version: str | None = None,
) -> ShardManifest:
    records_list = [dict(record) for record in records]
    shard_dir = root / run_id / "shards" / shard_id

    records_rel = "records.json"
    diagnostics_rel = "diagnostics.json"
    manifest_rel = "manifest.json"

    records_bytes = _json_bytes(records_list)
    diagnostics_bytes = _json_bytes(diagnostic.to_dict())

    atomic_create_bytes(shard_dir / records_rel, records_bytes)
    atomic_create_bytes(shard_dir / diagnostics_rel, diagnostics_bytes)

    manifest = ShardManifest(
        contract_version=CONTRACT_VERSION,
        run_id=run_id,
        shard_id=shard_id,
        created_at=utc_now_iso(),
        status=diagnostic.status,
        source_ids=list(source_ids),
        vacancy_count=len(records_list),
        records_file=records_rel,
        diagnostics_file=diagnostics_rel,
        records_sha256=sha256_bytes(records_bytes),
        diagnostics_sha256=sha256_bytes(diagnostics_bytes),
        producer_version=producer_version,
    )
    atomic_create_bytes(shard_dir / manifest_rel, _json_bytes(manifest.to_dict()))
    return manifest


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_shard_bundle(shard_dir: Path) -> tuple[ShardManifest, list[dict[str, Any]], dict[str, Any]]:
    manifest_payload = read_json(shard_dir / "manifest.json")
    manifest = ShardManifest(
        contract_version=manifest_payload["contract_version"],
        run_id=manifest_payload["run_id"],
        shard_id=manifest_payload["shard_id"],
        created_at=manifest_payload["created_at"],
        status=ShardStatus(manifest_payload["status"]),
        source_ids=list(manifest_payload["source_ids"]),
        vacancy_count=int(manifest_payload["vacancy_count"]),
        records_file=manifest_payload["records_file"],
        diagnostics_file=manifest_payload["diagnostics_file"],
        records_sha256=manifest_payload["records_sha256"],
        diagnostics_sha256=manifest_payload["diagnostics_sha256"],
        immutable=bool(manifest_payload.get("immutable", True)),
        producer_version=manifest_payload.get("producer_version"),
        metadata=dict(manifest_payload.get("metadata", {})),
    )

    if manifest.contract_version != CONTRACT_VERSION:
        raise ValueError(f"unsupported shard contract: {manifest.contract_version}")
    if not manifest.immutable:
        raise ValueError(f"mutable shard bundle rejected: {manifest.shard_id}")
    if manifest.records_file != "records.json" or manifest.diagnostics_file != "diagnostics.json":
        raise ValueError(f"unexpected artifact paths for shard {manifest.shard_id}")

    records_path = shard_dir / manifest.records_file
    diagnostics_path = shard_dir / manifest.diagnostics_file
    records_bytes = records_path.read_bytes()
    diagnostics_bytes = diagnostics_path.read_bytes()

    if sha256_bytes(records_bytes) != manifest.records_sha256:
        raise ValueError(f"records checksum mismatch for shard {manifest.shard_id}")
    if sha256_bytes(diagnostics_bytes) != manifest.diagnostics_sha256:
        raise ValueError(f"diagnostics checksum mismatch for shard {manifest.shard_id}")

    records = json.loads(records_bytes.decode("utf-8"))
    diagnostics = json.loads(diagnostics_bytes.decode("utf-8"))

    if not isinstance(records, list):
        raise ValueError(f"records payload is not a list for shard {manifest.shard_id}")
    if len(records) != manifest.vacancy_count:
        raise ValueError(f"vacancy count mismatch for shard {manifest.shard_id}")

    return manifest, records, diagnostics
