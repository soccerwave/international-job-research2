from __future__ import annotations

import copy
import unittest

from src.llm.dual_path_routing import (
    MAIN_FULL_REVIEW,
    RESCUE_TRIAGE,
    route_dual_path_candidates,
    routing_summary,
)


def job(job_id: str, *, seen_status: str = "SEEN") -> dict:
    return {
        "canonical_id": job_id,
        "position": {"title_raw": f"Job {job_id}"},
        "raw_extra": {
            "state_event": {"seen_status": seen_status},
            "evaluation": {"recommendation": "SKIP"},
        },
    }


class LLMDualPathRoutingL62Tests(unittest.TestCase):
    def test_main_routes_every_supplied_main_job_including_seen(self):
        rows = [
            job("main-seen", seen_status="SEEN"),
            job("main-new", seen_status="NEW"),
            job("main-changed", seen_status="MATERIALLY_CHANGED"),
        ]
        result = route_dual_path_candidates(
            rows,
            main_job_ids={"main-seen", "main-new", "main-changed"},
            rescue_candidate_job_ids=set(),
        )
        self.assertEqual(
            [row.job_id for row in result.main_full_review],
            ["main-seen", "main-new", "main-changed"],
        )
        self.assertTrue(all(row.route == MAIN_FULL_REVIEW for row in result.main_full_review))

    def test_main_has_precedence_over_rescue_overlap(self):
        rows = [job("overlap"), job("rescue-only")]
        result = route_dual_path_candidates(
            rows,
            main_job_ids={"overlap"},
            rescue_candidate_job_ids={"overlap", "rescue-only"},
        )
        self.assertEqual([row.job_id for row in result.main_full_review], ["overlap"])
        self.assertEqual([row.job_id for row in result.rescue_triage], ["rescue-only"])
        self.assertEqual(result.rescue_triage[0].route, RESCUE_TRIAGE)

    def test_duplicate_canonical_jobs_are_routed_once(self):
        rows = [job("same"), job("same"), job("rescue")]
        result = route_dual_path_candidates(
            rows,
            main_job_ids={"same"},
            rescue_candidate_job_ids={"rescue"},
        )
        self.assertEqual(len(result.main_full_review), 1)
        self.assertEqual(len(result.rescue_triage), 1)

    def test_missing_requested_ids_are_reported_without_invention(self):
        rows = [job("present-main"), job("present-rescue")]
        result = route_dual_path_candidates(
            rows,
            main_job_ids={"present-main", "missing-main"},
            rescue_candidate_job_ids={"present-rescue", "missing-rescue"},
        )
        self.assertEqual(result.missing_main_ids, ("missing-main",))
        self.assertEqual(result.missing_rescue_ids, ("missing-rescue",))

    def test_routing_does_not_mutate_rule_evaluation_or_jobs(self):
        rows = [job("main"), job("rescue")]
        original = copy.deepcopy(rows)
        route_dual_path_candidates(
            rows,
            main_job_ids={"main"},
            rescue_candidate_job_ids={"rescue"},
        )
        self.assertEqual(rows, original)

    def test_summary_keeps_paths_separate(self):
        rows = [job("m1"), job("m2"), job("r1")]
        result = route_dual_path_candidates(
            rows,
            main_job_ids={"m1", "m2"},
            rescue_candidate_job_ids={"r1"},
        )
        self.assertEqual(
            routing_summary(result),
            {
                "main_full_review": 2,
                "rescue_triage": 1,
                "selected_total": 3,
                "missing_main_ids": [],
                "missing_rescue_ids": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
