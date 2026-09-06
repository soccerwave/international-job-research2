from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.publish_control_plane_report import (
    CONTROL_PLANE_POINTER_VERSION,
    build_manifest,
    publish_report,
)


class FakeR2Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_order: list[str] = []

    def put_object(self, *, Bucket, Key, Body, **_kwargs):
        data = Body if isinstance(Body, bytes) else bytes(Body)
        self.objects[(Bucket, Key)] = data
        self.put_order.append(Key)
        return {"ETag": '"fake"'}

    def head_object(self, *, Bucket, Key):
        data = self.objects[(Bucket, Key)]
        return {"ContentLength": len(data)}

    def get_object(self, *, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


class ControlPlaneReportPublisherTests(unittest.TestCase):
    def _fixtures(self, root: Path) -> tuple[Path, Path, Path, dict]:
        summary = {
            "reporting_version": "REPORTING_V1.0.0",
            "run_id": "prod-123-1",
            "records_observed": 12,
            "current_actionable": 8,
            "today_actionable": 2,
            "state_generation": 3,
        }
        summary_path = root / "report_summary.json"
        report_path = root / "international_academic_job_report.xlsx"
        audit_path = root / "academic_job_report.xlsx"
        summary_path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
        report_path.write_bytes(b"PK\x03\x04clean-user-xlsx")
        audit_path.write_bytes(b"PK\x03\x04full-audit-xlsx")
        return summary_path, report_path, audit_path, summary

    def test_manifest_uses_run_scoped_keys_and_exact_digests(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary_path, report_path, audit_path, summary = self._fixtures(Path(tmp))
            manifest = build_manifest(
                summary_path=summary_path,
                report_path=report_path,
                audit_report_path=audit_path,
                github_run_id=123,
                github_run_attempt=2,
                commit="abc123",
                published_at="2026-09-05T00:00:00Z",
            )
            self.assertEqual(manifest["schema_version"], CONTROL_PLANE_POINTER_VERSION)
            self.assertEqual(manifest["project"], "international")
            self.assertEqual(manifest["production_run_id"], summary["run_id"])
            self.assertEqual(manifest["summary_key"], "control-plane/runs/123-2/report_summary.json")
            self.assertEqual(manifest["report_key"], "control-plane/runs/123-2/international_academic_job_report.xlsx")
            self.assertEqual(manifest["audit_report_key"], "control-plane/runs/123-2/international_academic_job_audit.xlsx")
            self.assertEqual(manifest["report_variant"], "USER_CLEAN_V1")
            self.assertEqual(
                manifest["summary_sha256"], hashlib.sha256(summary_path.read_bytes()).hexdigest()
            )
            self.assertEqual(
                manifest["report_sha256"], hashlib.sha256(report_path.read_bytes()).hexdigest()
            )
            self.assertEqual(
                manifest["audit_report_sha256"], hashlib.sha256(audit_path.read_bytes()).hexdigest()
            )
            self.assertEqual(manifest["records_observed"], 12)
            self.assertEqual(manifest["today_actionable"], 2)

    def test_latest_manifest_is_published_only_after_all_payloads_and_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path, report_path, audit_path, _summary = self._fixtures(root)
            evidence = root / "evidence.json"
            client = FakeR2Client()
            result = publish_report(
                client=client,
                bucket="international-academic-job-search",
                summary_path=summary_path,
                report_path=report_path,
                audit_report_path=audit_path,
                github_run_id=321,
                github_run_attempt=1,
                commit="def456",
                manifest_out=evidence,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(
                client.put_order,
                [
                    "control-plane/runs/321-1/report_summary.json",
                    "control-plane/runs/321-1/international_academic_job_report.xlsx",
                    "control-plane/runs/321-1/international_academic_job_audit.xlsx",
                    "control-plane/latest/manifest.json",
                ],
            )
            self.assertTrue(evidence.exists())
            persisted = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(persisted["manifest"]["github_run_id"], 321)


if __name__ == "__main__":
    unittest.main()
