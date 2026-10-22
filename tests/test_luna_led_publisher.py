from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from scripts.publish_control_plane_report import build_manifest


class LunaVariantManifestTests(unittest.TestCase):
    def test_explicit_variant_and_legacy_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.json"
            report = root / "report.xlsx"
            summary.write_text(json.dumps({"run_id": "prod-12-1", "records_observed": 12}))
            report.write_bytes(b"fake XLSX bytes - manifest only")
            args = dict(summary_path=summary, report_path=report,
                        github_run_id=12, github_run_attempt=1, commit="abc")
            self.assertEqual(build_manifest(**args)["report_variant"], "USER_CLEAN_V1")
            self.assertEqual(build_manifest(**args, report_variant="LUNA_LED_V1")["report_variant"], "LUNA_LED_V1")
            self.assertEqual(build_manifest(**args, report_variant="RULE_FALLBACK_V1")["report_variant"], "RULE_FALLBACK_V1")


if __name__ == "__main__":
    unittest.main()
