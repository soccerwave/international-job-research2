from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production.yml"
SECURE_ARTIFACT = ROOT / "scripts" / "secure_artifact.sh"


class Stage54ArtifactDurabilityTests(unittest.TestCase):
    def test_workflow_allows_diagnostics_without_shard_bundle(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('paths=()', text)
        self.assertIn('if [ -d "$base/shards/$shard" ]; then', text)
        self.assertIn('if [ -d "$base/diagnostics/$shard" ]; then', text)
        self.assertIn('if [ "${#paths[@]}" -eq 0 ]; then', text)
        self.assertNotIn('if [ ! -d "$base/shards/$shard" ]; then', text)

    def test_shard_artifact_upload_runs_on_failure_paths(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        marker = "- name: Upload encrypted production shard bundle"
        start = text.index(marker)
        block = text[start:start + 500]
        self.assertIn("if: always()", block)
        self.assertIn("retention-days: 2", block)
        self.assertIn("if-no-files-found: warn", block)

    def test_encrypted_roundtrip_supports_diagnostics_only_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "artifacts" / "run"
            diagnostic = base / "diagnostics" / "example-shard" / "source_lifecycle.jsonl"
            diagnostic.parent.mkdir(parents=True)
            diagnostic.write_text('{"event":"source_waiting"}\n', encoding="utf-8")
            encrypted = root / "diagnostics-only.tar.gz.enc"
            restored = root / "restored"
            env = dict(os.environ)
            env["ARTIFACT_ENCRYPTION_KEY"] = "stage54-test-key"

            subprocess.run(
                [
                    "bash",
                    str(SECURE_ARTIFACT),
                    "pack",
                    str(base),
                    str(encrypted),
                    "diagnostics/example-shard",
                ],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["bash", str(SECURE_ARTIFACT), "unpack", str(encrypted), str(restored)],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            restored_file = restored / "diagnostics" / "example-shard" / "source_lifecycle.jsonl"
            self.assertTrue(restored_file.exists())
            self.assertEqual(restored_file.read_text(encoding="utf-8"), diagnostic.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
