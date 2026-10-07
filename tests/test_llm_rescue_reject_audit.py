from __future__ import annotations

import copy
import unittest

from src.llm.dual_path_routing import route_dual_path_candidates
from src.llm.rescue_reject_audit import (
    ORIGIN_RESCUE_REJECT_AUDIT,
    rescue_reject_audit_summary,
    run_rescue_reject_audit,
    select_rescue_reject_audit_candidates,
)
from src.llm.rescue_triage import CLEARLY_OUT_OF_SCOPE, PASS_TO_FULL_REVIEW
from src.llm.shadow_evaluator import ShadowEvaluationError


def job(job_id: str) -> dict:
    return {
        "canonical_id": job_id,
        "position": {"title_raw": f"Job {job_id}"},
        "description": {"full_jd": f"Full JD for {job_id}", "detail_status": "FULL"},
    }


def triage(job_id: str, decision: str) -> dict:
    return {
        "job_id": job_id,
        "triage_id": f"triage-{job_id}",
        "llm_result": {"decision": decision},
    }


class FakeFullEvaluator:
    def __init__(self, *, fail_ids: set[str] | None = None):
        self.fail_ids = set(fail_ids or set())
        self.received: list[dict] = []

    def evaluate(self, canonical_job: dict) -> dict:
        self.received.append(copy.deepcopy(canonical_job))
        job_id = canonical_job["canonical_id"]
        if job_id in self.fail_ids:
            raise ShadowEvaluationError("synthetic failure")
        return {
            "evaluation_id": f"eval-{job_id}",
            "cache_hit": False,
            "input_tokens": 100,
            "output_tokens": 20,
            "llm_result": {"decision": "APPLY"},
        }


class RescueRejectAuditTests(unittest.TestCase):
    def _routing(self, n: int = 20):
        rows = [job(f"reject-{i:02d}") for i in range(n)] + [job("pass-1")]
        return route_dual_path_candidates(
            rows,
            main_job_ids=set(),
            rescue_candidate_job_ids={row["canonical_id"] for row in rows},
        )

    def test_samples_only_clearly_out_of_scope_and_caps_at_ten(self):
        routing = self._routing()
        triage_rows = [
            *(triage(f"reject-{i:02d}", CLEARLY_OUT_OF_SCOPE) for i in range(20)),
            triage("pass-1", PASS_TO_FULL_REVIEW),
        ]
        selected = select_rescue_reject_audit_candidates(
            routing,
            rescue_triage_records=triage_rows,
            run_id="prod-123-1",
            sample_size=10,
        )
        self.assertEqual(selected.population_size, 20)
        self.assertEqual(len(selected.candidates), 10)
        self.assertTrue(all(row.origin == ORIGIN_RESCUE_REJECT_AUDIT for row in selected.candidates))
        self.assertNotIn("pass-1", {row.job_id for row in selected.candidates})

    def test_sampling_is_reproducible_for_same_run(self):
        routing = self._routing()
        triage_rows = [triage(f"reject-{i:02d}", CLEARLY_OUT_OF_SCOPE) for i in range(20)]
        first = select_rescue_reject_audit_candidates(
            routing,
            rescue_triage_records=triage_rows,
            run_id="prod-123-1",
            sample_size=10,
        )
        second = select_rescue_reject_audit_candidates(
            routing,
            rescue_triage_records=list(reversed(triage_rows)),
            run_id="prod-123-1",
            sample_size=10,
        )
        self.assertEqual(
            [row.job_id for row in first.candidates],
            [row.job_id for row in second.candidates],
        )

    def test_different_run_ids_can_change_sample(self):
        routing = self._routing()
        triage_rows = [triage(f"reject-{i:02d}", CLEARLY_OUT_OF_SCOPE) for i in range(20)]
        first = select_rescue_reject_audit_candidates(
            routing,
            rescue_triage_records=triage_rows,
            run_id="prod-123-1",
            sample_size=10,
        )
        second = select_rescue_reject_audit_candidates(
            routing,
            rescue_triage_records=triage_rows,
            run_id="prod-124-1",
            sample_size=10,
        )
        self.assertNotEqual(
            [row.job_id for row in first.candidates],
            [row.job_id for row in second.candidates],
        )

    def test_full_evaluator_does_not_receive_triage_decision(self):
        routing = self._routing(3)
        triage_rows = [triage(f"reject-{i:02d}", CLEARLY_OUT_OF_SCOPE) for i in range(3)]
        selected = select_rescue_reject_audit_candidates(
            routing,
            rescue_triage_records=triage_rows,
            run_id="prod-123-1",
            sample_size=10,
        )
        evaluator = FakeFullEvaluator()
        run = run_rescue_reject_audit(selected, evaluator=evaluator)
        self.assertEqual(len(run.records), 3)
        for received in evaluator.received:
            self.assertNotIn("CLEARLY_OUT_OF_SCOPE", str(received))
            self.assertNotIn("RESCUE_REJECT_AUDIT", str(received))

    def test_summary_counts_favorable_full_reviews_and_failures(self):
        routing = self._routing(3)
        triage_rows = [triage(f"reject-{i:02d}", CLEARLY_OUT_OF_SCOPE) for i in range(3)]
        selected = select_rescue_reject_audit_candidates(
            routing,
            rescue_triage_records=triage_rows,
            run_id="prod-123-1",
            sample_size=10,
        )
        fail_id = selected.candidates[0].job_id
        run = run_rescue_reject_audit(selected, evaluator=FakeFullEvaluator(fail_ids={fail_id}))
        summary = rescue_reject_audit_summary(selected, run)
        self.assertEqual(summary["population_size"], 3)
        self.assertEqual(summary["selected_sample_size"], 3)
        self.assertEqual(summary["completed"], 2)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["favorable_full_reviews"], 2)


if __name__ == "__main__":
    unittest.main()
