from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable


class ShardStatus(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


class FinalizerStatus(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class ShardDiagnostic:
    shard_id: str
    source_ids: list[str]
    status: ShardStatus
    started_at: str
    finished_at: str
    elapsed_ms: int
    records_observed: int
    records_emitted: int
    detail_attempted: int = 0
    detail_succeeded: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(slots=True)
class ShardManifest:
    contract_version: str
    run_id: str
    shard_id: str
    created_at: str
    status: ShardStatus
    source_ids: list[str]
    vacancy_count: int
    records_file: str
    diagnostics_file: str
    records_sha256: str
    diagnostics_sha256: str
    immutable: bool = True
    producer_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(slots=True)
class FinalizerSummary:
    contract_version: str
    run_id: str
    status: FinalizerStatus
    started_at: str
    finished_at: str
    manifests_seen: int
    shards_accepted: int
    shards_rejected: int
    records_loaded: int
    records_emitted: int
    accepted_shards: list[str] = field(default_factory=list)
    rejected_shards: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


def normalize_vacancy_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stage 4 boundary only: preserve input records without scientific evaluation.

    Stage 3 owns the canonical vacancy contract. Stage 4 does not infer fit,
    mobility, language, blockers, or state semantics.
    """
    return [dict(record) for record in records]
