from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.state.r2_migration_retention import apply_migration_retention, plan_migration_retention
from src.state.r2_store import R2StateStore


class FakeR2Client:
    def __init__(self, objects):
        self.objects = list(objects)
        self.deleted = []

    def list_objects_v2(self, **kwargs):
        prefix = kwargs["Prefix"]
        return {
            "IsTruncated": False,
            "Contents": [obj for obj in self.objects if obj["Key"].startswith(prefix)],
        }

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs["Key"])
        return {}


def obj(key: str, *, age_days: int, now: datetime, size_mb: int = 100):
    return {
        "Key": key,
        "Size": size_mb * 1024 * 1024,
        "LastModified": now - timedelta(days=age_days),
    }


class R2MigrationRetentionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    def test_old_migration_snapshots_are_candidates(self):
        objects = [
            obj("state/migrations/dvs/old.json", age_days=20, now=self.now),
            obj("state/migrations/evaluation-dimensions/recent.json", age_days=1, now=self.now),
        ]
        plan = plan_migration_retention(R2StateStore(FakeR2Client(objects), "bucket"), max_age_days=14, now=self.now)
        self.assertEqual(plan.delete_keys, ("state/migrations/dvs/old.json",))
        self.assertEqual(plan.snapshots, 2)

    def test_recent_migration_snapshots_are_kept(self):
        objects = [obj("state/migrations/dvs/recent.json", age_days=13, now=self.now)]
        plan = plan_migration_retention(R2StateStore(FakeR2Client(objects), "bucket"), max_age_days=14, now=self.now)
        self.assertEqual(plan.delete_keys, ())

    def test_only_migration_prefix_is_scanned(self):
        objects = [
            obj("state/migrations/dvs/old.json", age_days=20, now=self.now),
            obj("state/backups/g00000001-prod-old.json", age_days=20, now=self.now),
        ]
        plan = plan_migration_retention(R2StateStore(FakeR2Client(objects), "bucket"), max_age_days=14, now=self.now)
        self.assertEqual(plan.snapshots, 1)
        self.assertEqual(plan.delete_keys, ("state/migrations/dvs/old.json",))

    def test_apply_deletes_only_planned_keys(self):
        objects = [obj("state/migrations/dvs/old.json", age_days=20, now=self.now)]
        client = FakeR2Client(objects)
        store = R2StateStore(client, "bucket")
        plan = plan_migration_retention(store, max_age_days=14, now=self.now)
        result = apply_migration_retention(store, plan)
        self.assertEqual(result["deleted_count"], 1)
        self.assertEqual(client.deleted, ["state/migrations/dvs/old.json"])


if __name__ == "__main__":
    unittest.main()
