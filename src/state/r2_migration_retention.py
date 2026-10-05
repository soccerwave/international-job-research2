from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .r2_store import R2StateStore


@dataclass(frozen=True)
class MigrationSnapshot:
    key: str
    size: int
    last_modified: datetime


@dataclass(frozen=True)
class MigrationRetentionPlan:
    snapshots: int
    delete_keys: tuple[str, ...]
    delete_bytes: int
    kept_bytes: int


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _list_migration_snapshots(store: R2StateStore) -> list[MigrationSnapshot]:
    prefix = store.key("state/migrations") + "/"
    token: str | None = None
    snapshots: list[MigrationSnapshot] = []

    while True:
        kwargs: dict[str, Any] = {"Bucket": store.bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        response = store.client.list_objects_v2(**kwargs)
        for obj in response.get("Contents") or []:
            key = str(obj.get("Key") or "")
            modified = obj.get("LastModified")
            if not key or not isinstance(modified, datetime):
                continue
            snapshots.append(
                MigrationSnapshot(
                    key=key,
                    size=int(obj.get("Size") or 0),
                    last_modified=_as_utc(modified),
                )
            )
        if not response.get("IsTruncated"):
            break
        token = str(response.get("NextContinuationToken") or "").strip() or None
        if token is None:
            raise RuntimeError("R2 migration listing was truncated without a continuation token")

    return snapshots


def plan_migration_retention(
    store: R2StateStore,
    *,
    max_age_days: int = 14,
    now: datetime | None = None,
) -> MigrationRetentionPlan:
    if max_age_days < 1:
        raise ValueError("max_age_days must be >= 1")

    snapshots = _list_migration_snapshots(store)
    reference = _as_utc(now or datetime.now(timezone.utc))
    cutoff = reference - timedelta(days=max_age_days)
    delete = [item for item in snapshots if item.last_modified < cutoff]
    delete_keys = {item.key for item in delete}
    kept = [item for item in snapshots if item.key not in delete_keys]

    return MigrationRetentionPlan(
        snapshots=len(snapshots),
        delete_keys=tuple(sorted(item.key for item in delete)),
        delete_bytes=sum(item.size for item in delete),
        kept_bytes=sum(item.size for item in kept),
    )


def apply_migration_retention(store: R2StateStore, plan: MigrationRetentionPlan) -> dict[str, Any]:
    deleted: list[str] = []
    for key in plan.delete_keys:
        store.client.delete_object(Bucket=store.bucket, Key=key)
        deleted.append(key)
    return {
        "deleted_count": len(deleted),
        "deleted_bytes": plan.delete_bytes,
        "deleted_keys": deleted,
    }
