from __future__ import annotations

import unittest

from scripts.capture_stage7_reference import (
    is_candidate_anchor,
    normalize_url,
    reference_id,
)


class Stage72ReferenceCaptureTests(unittest.TestCase):
    def test_normalize_url_removes_fragment_and_tracking(self):
        value = normalize_url(
            "https://example.edu/jobs/",
            "/jobs/123?utm_source=test&keep=1#apply",
        )
        self.assertEqual(value, "https://example.edu/jobs/123?keep=1")

    def test_candidate_anchor_accepts_jobish_url(self):
        self.assertTrue(
            is_candidate_anchor(
                "https://example.edu/",
                "/vacancies/123",
                "Project ABC",
            )
        )

    def test_candidate_anchor_accepts_target_role_text(self):
        self.assertTrue(
            is_candidate_anchor(
                "https://example.edu/",
                "/detail/123",
                "Postdoctoral Research Fellow in Neuroscience",
            )
        )

    def test_candidate_anchor_rejects_navigation(self):
        self.assertFalse(
            is_candidate_anchor(
                "https://example.edu/",
                "/about",
                "About us",
            )
        )

    def test_reference_id_is_stable_and_source_scoped(self):
        url = "https://example.edu/jobs/123"
        first = reference_id("source_a", url)
        self.assertEqual(first, reference_id("source_a", url))
        self.assertNotEqual(first, reference_id("source_b", url))
        self.assertTrue(first.startswith("ref-"))


if __name__ == "__main__":
    unittest.main()
