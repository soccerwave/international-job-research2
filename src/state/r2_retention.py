from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .r2_store import R2StateStore

_PRODUCTION_BACKUP_RE = re.compile(r"^g(?P<generation>\d+)-prod-[A-Za-z0-9_.-]+\.json$")


@dataclass(frozen=True)
class BackupObject:
    key: str
    generation: int
    size: int
    last_modified: datetime


@dataclass(frozen=True)
class RetentionPlan:
    production_backups: int
    protected_latest: tuple[str, ...]
    delete_keys: tuple[str, ...]
    delete_bytes: int
    kept_bytes: int
    untouched_nonproduction: int


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _list_backup_objects(store: R2StateStore) -> tuple[list[BackupObject], int]:
    # R2StateStore.key() intentionally strips trailing slashes. Listing a logical
    # directory therefore needs to add the separator back before slicing relative keys.
    prefix = store.key("state/backups") + "/"
    token: str | None = None
    production: list[BackupObject] = []
    untouched_nonproduction = 0

    while True:
        kwargs: dict[str, Any] = {"Bucket": store.bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        response = store.client.list_objects_v2(**kwargs)
        for obj in response.get("Contents") or []:
            key = str(obj.get("Key") or "")
            relative = key[len(prefix):] if key.startswith(prefix) else key
            match = _PRODUCTION_BACKUP_RE.fullmatch(relative)
            if not match:
                untouched_nonproduction += 1
                continue
            modified = obj.get("LastModified")
            if not isinstance(modified, datetime):
                # Unknown age must never be a delete candidate.
                untouched_nonproduction += 1
                continue
            production.append(
                BackupObject(
                    key=key,
                    generation=int(match.group("generation")),
                    size=int(obj.get("Size") or 0),
                    last_modified=_as_utc(modified),
                )
            )
        if not response.get("IsTruncated"):
            break
        token = str(response.get("NextContinuationToken") or "").strip() or None
        if token is None:
            raise RuntimeError("R2 backup listing was truncated without a continuation token")

    return production, untouched_nonproduction


def plan_backup_retention(
    store: R2StateStore,
    *,
    max_age_days: int = 7,
    keep_latest: int = 3,
    now: datetime | None = None,
) -> RetentionPlan:
    if max_age_days < 1:
        raise ValueError("max_age_days must be >= 1")
    if keep_latest < 1:
        raise ValueError("keep_latest must be >= 1")

    production, untouched_nonproduction = _list_backup_objects(store)
    reference = _as_utc(now or datetime.now(timezone.utc))
    cutoff = reference - timedelta(days=max_age_days)

    newest = sorted(production, key=lambda item: (item.generation, item.last_modified), reverse=True)
    protected = {item.key for item in newest[:keep_latest]}
    delete = [item for item in production if item.key not in protected and item.last_modified < cutoff]
    delete_key_set = {candidate.key for candidate in delete}
    kept = [item for item in production if item.key not in delete_key_set]

    return RetentionPlan(
        production_backups=len(production),
        protected_latest=tuple(item.key for item in newest[:keep_latest]),
        delete_keys=tuple(sorted(item.key for item in delete)),
        delete_bytes=sum(item.size for item in delete),
        kept_bytes=sum(item.size for item in kept),
        untouched_nonproduction=untouched_nonproduction,
    )


def apply_backup_retention(store: R2StateStore, plan: RetentionPlan) -> dict[str, Any]:
    deleted: list[str] = []
    for key in plan.delete_keys:
        store.client.delete_object(Bucket=store.bucket, Key=key)
        deleted.append(key)
    return {
        "deleted_count": len(deleted),
        "deleted_bytes": plan.delete_bytes,
        "deleted_keys": deleted,
        "protected_latest": list(plan.protected_latest),
        "untouched_nonproduction": plan.untouched_nonproduction,
    }
