from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.publish_llm_shadow_report import (
    POINTER_VERSION,
    build_manifest,
    publish_llm_shadow_report,
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
        return {"ContentLength": len(self.objects[(Bucket, Key)])}

    def get_object(self, *, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


class LLMShadowR2LatestReportTests(unittest.TestCase):
    def _fixtures(self, root: Path):
        summary = {
            "status": "PASS",
            "shadow_only": True,
            "production_authority_unchanged": True,
            "run_id": "prod-123-1",
            "model": "gpt-6-luna",
            "candidate_profile_version": "LLM_CANDIDATE_PROFILE_V1.1.0",
            "report": {
                "main_rows": 20,
                "llm_rescued_rows": 3,
                "disagreement_rows": 4,
            },
            "failures": 0,
        }
        summary_path = root / "shadow_summary.json"
        report_path = root / "llm_shadow_report.xlsx"
        summary_path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
        report_path.write_bytes(b"PK\x03\x04llm-shadow-xlsx")
        return summary_path, report_path, summary

    def test_manifest_uses_dedicated_llm_report_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary_path, report_path, _ = self._fixtures(Path(tmp))
            manifest = build_manifest(
                summary_path=summary_path,
                report_path=report_path,
                production_run_id="prod-123-1",
                github_run_id=123,
                github_run_attempt=1,
                commit="abc123",
                published_at="2026-10-07T10:00:00Z",
            )
            self.assertEqual(manifest["schema_version"], POINTER_VERSION)
            self.assertEqual(manifest["report_variant"], "LLM_SHADOW_V0.1")
            self.assertEqual(manifest["summary_key"], "llm/reports/runs/123-1/shadow_summary.json")
            self.assertEqual(manifest["report_key"], "llm/reports/runs/123-1/llm_shadow_report.xlsx")
            self.assertEqual(manifest["model"], "gpt-6-luna")
            self.assertTrue(manifest["production_authority_unchanged"])

    def test_latest_pointer_is_written_only_after_report_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path, report_path, _ = self._fixtures(root)
            evidence = root / "publish.json"
            client = FakeR2Client()
            result = publish_llm_shadow_report(
                client=client,
                bucket="international-academic-job-search",
                summary_path=summary_path,
                report_path=report_path,
                production_run_id="prod-123-1",
                github_run_id=123,
                github_run_attempt=1,
                commit="abc123",
                manifest_out=evidence,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(
                client.put_order,
                [
                    "llm/reports/runs/123-1/shadow_summary.json",
                    "llm/reports/runs/123-1/llm_shadow_report.xlsx",
                    "llm/reports/latest/manifest.json",
                ],
            )
            self.assertTrue(evidence.exists())
            latest = json.loads(
                client.objects[
                    ("international-academic-job-search", "llm/reports/latest/manifest.json")
                ].decode("utf-8")
            )
            self.assertEqual(latest["report_key"], "llm/reports/runs/123-1/llm_shadow_report.xlsx")

    def test_mismatched_run_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary_path, report_path, _ = self._fixtures(Path(tmp))
            with self.assertRaises(ValueError):
                build_manifest(
                    summary_path=summary_path,
                    report_path=report_path,
                    production_run_id="prod-999-1",
                    github_run_id=123,
                    github_run_attempt=1,
                    commit="abc123",
                )


if __name__ == "__main__":
    unittest.main()
