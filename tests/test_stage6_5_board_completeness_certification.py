from __future__ import annotations

import contextlib
import io
import json
import unittest

from scripts.verify_stage6_board_completeness import main


class Stage65BoardCompletenessCertificationTests(unittest.TestCase):
    def test_stage6_board_completeness_certification_passes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = main()
        payload = json.loads(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["profile"], "STAGE_6_BOARD_COMPLETENESS_CERTIFICATION")
        self.assertTrue(payload["checks"])
        self.assertTrue(all(payload["checks"].values()))
        self.assertEqual(payload["behavior"], "READ_ONLY_CERTIFICATION")
        self.assertEqual(payload["stage6_scope"], "BOARD_COMPLETENESS_STRUCTURE_ONLY")
        self.assertEqual(payload["next_stage"], "STAGE_7_RECALL_MEASUREMENT")
        self.assertEqual(payload["summary"]["confirmed_structural_gap_ids"], ["uniroles_au"])


if __name__ == "__main__":
    unittest.main()
