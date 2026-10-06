from __future__ import annotations

import copy
import unittest

from src.llm.dual_path_routing import route_dual_path_candidates
from src.llm.full_evaluation_routing import (
    ORIGIN_LLM_RESCUE,
    ORIGIN_MAIN,
    full_evaluation_summary,
    run_full_evaluations,
    select_full_review_candidates,
)
from src.llm.rescue_triage import CLEARLY_OUT_OF_SCOPE, PASS_TO_FULL_REVIEW
from src.llm.shadow_evaluator import ShadowEvaluationError


def job(job_id: str) -> dict:
    return {
        "canonical_id": job_id,
        "position": {"title_raw": f"Job {job_id}"},
        "description": {"full_jd": f"Full JD for {job_id}", "detail_status": "FULL"},
        "raw_extra": {
            "evaluation": {
                "recommendation": "SKIP",
                "reason": "RULE_REASON_MUST_NOT_BE_USED_FOR_ROUTING",
            }
        },
    }


def triage(job_id: str, decision: str, triage_id: str | None = None) -> dict:
    return {
        "job_id": job_id,
        "triage_id": triage_id or f"triage-{job_id}",
        "llm_result": {"decision": decision},
    }


class FakeFullEvaluator:
    def __init__(self, *, cache_hit_ids: set[str] | None = None, fail_ids: set[str] | None = None):
        self.cache_hit_ids = set(cache_hit_ids or set())
        self.fail_ids = set(fail_ids or set())
        self.received: list[dict] = []

    def evaluate(self, canonical_job: dict) -> dict:
        self.received.append(copy.deepcopy(canonical_job))
        job_id = canonical_job["canonical_id"]
        if job_id in self.fail_ids:
            raise ShadowEvaluationError("synthetic failure")
        return {
            "job_id": job_id,
            "cache_hit": job_id in self.cache_hit_ids,
            "llm_result": {"decision": "APPLY"},
        }


class LLMFullEvaluationRoutingL71Tests(unittest.TestCase):
    def _routing(self):
        rows = [job("main-1"), job("main-2"), job("rescue-pass"), job("rescue-reject"), job("rescue-missing")]
        return route_dual_path_candidates(
            rows,
            main_job_ids={"main-1", "main-2"},
            rescue_candidate_job_ids={"rescue-pass", "rescue-reject", "rescue-missing"},
        )

    def test_all_main_jobs_always_go_to_full_review(self):
        routing = self._routing()
        selection = select_full_review_candidates(
            routing,
            rescue_triage_records=[],
        )
        main_ids = [row.job_id for row in selection.candidates if row.origin == ORIGIN_MAIN]
        self.assertEqual(main_ids, ["main-1", "main-2"])

    def test_only_passed_rescue_jobs_go_to_full_review(self):
        routing = self._routing()
        selection = select_full_review_candidates(
            routing,
            rescue_triage_records=[
                triage("rescue-pass", PASS_TO_FULL_REVIEW),
                triage("rescue-reject", CLEARLY_OUT_OF_SCOPE),
            ],
        )
        rescue = [row for row in selection.candidates if row.origin == ORIGIN_LLM_RESCUE]
        self.assertEqual([row.job_id for row in rescue], ["rescue-pass"])
        self.assertEqual(rescue[0].triage_id, "triage-rescue-pass")
        self.assertEqual(selection.rescue_rejected_ids, ("rescue-reject",))
        self.assertEqual(selection.rescue_missing_triage_ids, ("rescue-missing",))

    def test_main_does_not_depend_on_triage_result(self):
        rows = [job("overlap")]
        routing = route_dual_path_candidates(
            rows,
            main_job_ids={"overlap"},
            rescue_candidate_job_ids={"overlap"},
        )
        selection = select_full_review_candidates(
            routing,
            rescue_triage_records=[triage("overlap", CLEARLY_OUT_OF_SCOPE)],
        )
        self.assertEqual(len(selection.candidates), 1)
        self.assertEqual(selection.candidates[0].origin, ORIGIN_MAIN)

    def test_full_evaluator_receives_unchanged_canonical_job_without_route_metadata(self):
        routing = self._routing()
        selection = select_full_review_candidates(
            routing,
            rescue_triage_records=[triage("rescue-pass", PASS_TO_FULL_REVIEW)],
        )
        originals = {row.job_id: copy.deepcopy(row.job) for row in selection.candidates}
        evaluator = FakeFullEvaluator()
        run_full_evaluations(selection, evaluator=evaluator)

        received_by_id = {row["canonical_id"]: row for row in evaluator.received}
        self.assertEqual(set(received_by_id), set(originals))
        for job_id, original in originals.items():
            self.assertEqual(received_by_id[job_id], original)
            serialized = str(received_by_id[job_id])
            self.assertNotIn("MAIN_FULL_REVIEW", serialized)
            self.assertNotIn("LLM_RESCUE", serialized)
            self.assertNotIn("PASS_TO_FULL_REVIEW", serialized)

    def test_provenance_is_attached_after_evaluation(self):
        routing = self._routing()
        selection = select_full_review_candidates(
            routing,
            rescue_triage_records=[triage("rescue-pass", PASS_TO_FULL_REVIEW)],
        )
        evaluator = FakeFullEvaluator()
        run = run_full_evaluations(selection, evaluator=evaluator)
        by_id = {row.job_id: row for row in run.records}
        self.assertEqual(by_id["main-1"].origin, ORIGIN_MAIN)
        self.assertIsNone(by_id["main-1"].triage_id)
        self.assertEqual(by_id["rescue-pass"].origin, ORIGIN_LLM_RESCUE)
        self.assertEqual(by_id["rescue-pass"].triage_id, "triage-rescue-pass")

    def test_failures_are_recorded_without_blocking_other_jobs(self):
        routing = self._routing()
        selection = select_full_review_candidates(
            routing,
            rescue_triage_records=[triage("rescue-pass", PASS_TO_FULL_REVIEW)],
        )
        evaluator = FakeFullEvaluator(fail_ids={"main-1"})
        run = run_full_evaluations(selection, evaluator=evaluator)
        self.assertEqual(len(run.failures), 1)
        self.assertEqual(run.failures[0]["job_id"], "main-1")
        self.assertEqual({row.job_id for row in run.records}, {"main-2", "rescue-pass"})

    def test_summary_distinguishes_cache_hits_from_real_api_work(self):
        routing = self._routing()
        selection = select_full_review_candidates(
            routing,
            rescue_triage_records=[
                triage("rescue-pass", PASS_TO_FULL_REVIEW),
                triage("rescue-reject", CLEARLY_OUT_OF_SCOPE),
            ],
        )
        evaluator = FakeFullEvaluator(cache_hit_ids={"main-1", "rescue-pass"})
        run = run_full_evaluations(selection, evaluator=evaluator)
        summary = full_evaluation_summary(selection, run)

        self.assertEqual(summary["selected_main"], 2)
        self.assertEqual(summary["selected_rescue"], 1)
        self.assertEqual(summary["rescue_rejected"], 1)
        self.assertEqual(summary["rescue_missing_triage"], 1)
        self.assertEqual(summary["cache_hits"], 2)
        self.assertEqual(summary["api_evaluations"], 1)
        self.assertEqual(summary["completed_by_origin"][ORIGIN_MAIN], 2)
        self.assertEqual(summary["completed_by_origin"][ORIGIN_LLM_RESCUE], 1)


if __name__ == "__main__":
    unittest.main()
