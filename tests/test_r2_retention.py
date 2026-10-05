from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.state.r2_retention import apply_backup_retention, plan_backup_retention
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
        self.objects = [obj for obj in self.objects if obj["Key"] != kwargs["Key"]]
        return {}


def obj(key: str, *, age_days: int, generation_size_mb: int = 100, now: datetime):
    return {
        "Key": key,
        "Size": generation_size_mb * 1024 * 1024,
        "LastModified": now - timedelta(days=age_days),
    }


class R2RetentionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    def test_old_production_backups_are_pruned_but_latest_three_are_protected(self):
        objects = [
            obj("state/backups/g00000035-prod-old-1.json", age_days=20, now=self.now),
            obj("state/backups/g00000036-prod-old-2.json", age_days=19, now=self.now),
            obj("state/backups/g00000037-prod-old-3.json", age_days=18, now=self.now),
            obj("state/backups/g00000038-prod-recent-1.json", age_days=2, now=self.now),
            obj("state/backups/g00000039-prod-recent-2.json", age_days=1, now=self.now),
            obj("state/backups/g00000041-prod-recent-3.json", age_days=0, now=self.now),
        ]
        store = R2StateStore(FakeR2Client(objects), "bucket")
        plan = plan_backup_retention(store, max_age_days=7, keep_latest=3, now=self.now)
        self.assertEqual(len(plan.delete_keys), 3)
        self.assertEqual(
            set(plan.protected_latest),
            {
                "state/backups/g00000038-prod-recent-1.json",
                "state/backups/g00000039-prod-recent-2.json",
                "state/backups/g00000041-prod-recent-3.json",
            },
        )

    def test_nonproduction_manual_backup_is_never_deleted(self):
        objects = [
            obj("state/backups/g00000001-prod-old.json", age_days=30, now=self.now),
            obj("state/backups/g00000040-dvs-identity-repair-2026-10-04.json", age_days=30, now=self.now),
            obj("state/backups/g00000041-prod-new.json", age_days=0, now=self.now),
        ]
        client = FakeR2Client(objects)
        store = R2StateStore(client, "bucket")
        plan = plan_backup_retention(store, max_age_days=7, keep_latest=1, now=self.now)
        self.assertEqual(plan.untouched_nonproduction, 1)
        self.assertNotIn("state/backups/g00000040-dvs-identity-repair-2026-10-04.json", plan.delete_keys)
        apply_backup_retention(store, plan)
        self.assertIn("state/backups/g00000001-prod-old.json", client.deleted)
        self.assertNotIn("state/backups/g00000040-dvs-identity-repair-2026-10-04.json", client.deleted)

    def test_recent_backups_survive_even_beyond_latest_three(self):
        objects = [
            obj(f"state/backups/g{generation:08d}-prod-r{generation}.json", age_days=age, now=self.now)
            for generation, age in [(10, 6), (11, 5), (12, 4), (13, 3), (14, 2)]
        ]
        store = R2StateStore(FakeR2Client(objects), "bucket")
        plan = plan_backup_retention(store, max_age_days=7, keep_latest=3, now=self.now)
        self.assertEqual(plan.delete_keys, ())

    def test_prefix_isolation_only_scans_store_prefix(self):
        objects = [
            obj("acceptance/run-1/state/backups/g00000001-prod-old.json", age_days=30, now=self.now),
            obj("state/backups/g00000001-prod-old.json", age_days=30, now=self.now),
        ]
        store = R2StateStore(FakeR2Client(objects), "bucket", "acceptance/run-1")
        plan = plan_backup_retention(store, max_age_days=7, keep_latest=1, now=self.now)
        self.assertEqual(plan.production_backups, 1)
        self.assertEqual(plan.delete_keys, ())


if __name__ == "__main__":
    unittest.main()
