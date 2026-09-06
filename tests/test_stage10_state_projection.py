from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.runtime.canonicalizer import canonicalize_records
from src.runtime.preprod import evaluate_canonical_records, persist_preprod_state
from tests.test_stage10_preprod import _full_detail, _job


class Stage10StateIdentityProjectionTests(unittest.TestCase):
    def test_shared_board_listing_url_does_not_collapse_distinct_vacancies(self):
        detail = _full_detail()
        board_url = "https://example.org/board/jobs"
        records = []
        for job_id in ("101", "102", "103"):
            record = _job(job_id, source_key="board", detail=detail)
            record["source"]["listing_url"] = board_url
            records.append(record)

        canonical, canonical_summary = canonicalize_records(records)
        self.assertEqual(canonical_summary["canonical_records"], 3)
        self.assertEqual(len({record["canonical_id"] for record in canonical}), 3)
        evaluate_canonical_records(canonical)
        original_listing_urls = [record["source"]["listing_url"] for record in canonical]

        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            first, first_projection = persist_preprod_state(
                canonical,
                state_backend="LOCAL",
                state_path=state_path,
                observed_at="2026-09-04T20:00:00+00:00",
                run_id="stage10-projection-first",
            )

            self.assertEqual(first.summary["NEW"], 3)
            self.assertEqual(first.summary["SEEN"], 0)
            self.assertEqual(first.summary["MATERIALLY_CHANGED"], 0)
            self.assertEqual(first.summary["REOPENED"], 0)
            self.assertEqual(first.summary["state_jobs"], 3)
            self.assertEqual(first_projection["repeated_url_alias_values"], 1)
            self.assertEqual(first_projection["suppressed_by_field"]["listing_url"], 3)
            self.assertTrue(first_projection["state_id_cardinality_matches_records"])
            self.assertEqual([record["source"]["listing_url"] for record in canonical], original_listing_urls)
            self.assertEqual(len({record["raw_extra"]["state"]["state_id"] for record in canonical}), 3)

            second, second_projection = persist_preprod_state(
                canonical,
                state_backend="LOCAL",
                state_path=state_path,
                observed_at="2026-09-04T20:00:01+00:00",
                run_id="stage10-projection-replay",
            )

            self.assertEqual(second.summary["NEW"], 0)
            self.assertEqual(second.summary["SEEN"], 3)
            self.assertEqual(second.summary["MATERIALLY_CHANGED"], 0)
            self.assertEqual(second.summary["REOPENED"], 0)
            self.assertEqual(second.summary["state_jobs"], 3)
            self.assertEqual(second.summary["not_observed_inferred_closed"], 0)
            self.assertTrue(second_projection["state_id_cardinality_matches_records"])
            self.assertEqual([record["source"]["listing_url"] for record in canonical], original_listing_urls)


if __name__ == "__main__":
    unittest.main()
