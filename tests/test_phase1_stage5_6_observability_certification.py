from __future__ import annotations

import contextlib
import io
import json
import unittest

from scripts.verify_stage5_observability import main


class Stage56ObservabilityCertificationTests(unittest.TestCase):
    def test_stage5_observability_certification_passes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = main()
        payload = json.loads(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["profile"], "STAGE_5_OBSERVABILITY_CERTIFICATION")
        self.assertTrue(payload["checks"])
        self.assertTrue(all(payload["checks"].values()))
        self.assertEqual(payload["behavior"], "READ_ONLY_CERTIFICATION")


if __name__ == "__main__":
    unittest.main()
