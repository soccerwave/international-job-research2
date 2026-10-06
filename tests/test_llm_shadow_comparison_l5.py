from __future__ import annotations

import copy
import unittest

from src.llm.shadow_comparison import (
    ShadowComparisonError,
    compare_available_shadow_results,
    compare_shadow_result,
    comparison_summary,
)


def canonical_job(job_id: str, recommendation: str) -> dict:
    return {
        "canonical_id": job_id,
        "raw_extra": {
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": recommendation,
                "reason": "deterministic reason should remain post-hoc only",
                "fit_signals": ["rule keyword hit"],
            }
        },
    }


def shadow(job_id: str, decision: str, *, fit_score: int = 70, confidence: int = 80) -> dict:
    return {
        "shadow_schema_version": "LLM_SHADOW_RESULT_V0.1",
        "evaluation_id": f"eval-{job_id}",
        "job_id": job_id,
        "candidate_profile_version": "LLM_CANDIDATE_PROFILE_V1.1.0",
        "llm_result": {
            "schema_version": "LLM_EVALUATION_V0.1",
            "evaluation_id": f"eval-{job_id}",
            "decision": decision,
            "fit_score": fit_score,
            "confidence": confidence,
            "domain_fit": 70,
            "methods_fit": 70,
            "seniority_fit": 70,
            "eligibility_risk": "LOW",
            "transferable_fit": 70,
            "hard_blocker": False,
            "hard_blocker_reason": None,
            "reason_short": "Independent semantic result.",
            "evidence_quality": "FULL_JD",
        },
    }


class LLMShadowComparisonL5Tests(unittest.TestCase):
    def test_rule_skip_llm_strong_apply_is_explicit_false_negative_candidate_tag(self):
        row = compare_shadow_result(canonical_job("a", "SKIP"), shadow("a", "STRONG_APPLY", fit_score=93))
        self.assertEqual(row["direction"], "LLM_UPRANK")
        self.assertEqual(row["decision_distance"], 4)
        self.assertIn("RULE_SKIP_LLM_STRONG_APPLY", row["disagreement_tags"])
        self.assertIn("DECISION_DISTANCE_GE_2", row["disagreement_tags"])

    def test_rule_skip_llm_apply_is_explicit_tag(self):
        row = compare_shadow_result(canonical_job("b", "SKIP"), shadow("b", "APPLY"))
        self.assertIn("RULE_SKIP_LLM_APPLY", row["disagreement_tags"])
        self.assertTrue(row["is_disagreement"])

    def test_rule_review_llm_apply_is_explicit_tag(self):
        row = compare_shadow_result(canonical_job("c", "REVIEW"), shadow("c", "APPLY"))
        self.assertIn("RULE_REVIEW_LLM_APPLY", row["disagreement_tags"])
        self.assertEqual(row["decision_distance"], 1)

    def test_rule_apply_llm_skip_is_explicit_tag(self):
        row = compare_shadow_result(canonical_job("d", "APPLY"), shadow("d", "SKIP", fit_score=12))
        self.assertIn("RULE_APPLY_LLM_SKIP", row["disagreement_tags"])
        self.assertEqual(row["direction"], "LLM_DOWNRANK")
        self.assertEqual(row["decision_distance"], -3)

    def test_low_priority_up_rank_is_visible(self):
        row = compare_shadow_result(canonical_job("e", "LOW_PRIORITY"), shadow("e", "APPLY"))
        self.assertIn("RULE_LOW_PRIORITY_LLM_APPLY", row["disagreement_tags"])
        self.assertEqual(row["decision_distance"], 2)

    def test_agreement_has_no_disagreement_tags(self):
        row = compare_shadow_result(canonical_job("f", "APPLY"), shadow("f", "APPLY"))
        self.assertFalse(row["is_disagreement"])
        self.assertEqual(row["direction"], "AGREEMENT")
        self.assertEqual(row["disagreement_tags"], [])

    def test_rule_score_is_not_invented(self):
        row = compare_shadow_result(canonical_job("g", "REVIEW"), shadow("g", "STRONG_APPLY", fit_score=88))
        self.assertIsNone(row["rule_score"])
        self.assertEqual(row["llm_fit_score"], 88)
        self.assertEqual(row["score_comparison_status"], "UNAVAILABLE_NO_RULE_COMPOSITE_SCORE")

    def test_comparison_does_not_mutate_rule_or_shadow_inputs(self):
        job = canonical_job("h", "SKIP")
        result = shadow("h", "APPLY")
        job_before = copy.deepcopy(job)
        result_before = copy.deepcopy(result)
        compare_shadow_result(job, result)
        self.assertEqual(job, job_before)
        self.assertEqual(result, result_before)

    def test_job_id_mismatch_is_rejected(self):
        with self.assertRaises(ShadowComparisonError):
            compare_shadow_result(canonical_job("i", "SKIP"), shadow("other", "APPLY"))

    def test_batch_join_only_compares_jobs_with_actual_shadow_results(self):
        jobs = [canonical_job("j1", "SKIP"), canonical_job("j2", "APPLY"), canonical_job("j3", "REVIEW")]
        rows = compare_available_shadow_results(jobs, [shadow("j1", "APPLY"), shadow("j3", "REVIEW")])
        self.assertEqual({row["job_id"] for row in rows}, {"j1", "j3"})
        self.assertEqual(len(rows), 2)

    def test_duplicate_shadow_result_is_rejected(self):
        jobs = [canonical_job("k", "SKIP")]
        with self.assertRaises(ShadowComparisonError):
            compare_available_shadow_results(jobs, [shadow("k", "APPLY"), shadow("k", "APPLY")])

    def test_summary_counts_key_disagreement_classes(self):
        rows = [
            compare_shadow_result(canonical_job("l1", "SKIP"), shadow("l1", "STRONG_APPLY")),
            compare_shadow_result(canonical_job("l2", "REVIEW"), shadow("l2", "APPLY")),
            compare_shadow_result(canonical_job("l3", "APPLY"), shadow("l3", "APPLY")),
        ]
        summary = comparison_summary(rows)
        self.assertEqual(summary["compared"], 3)
        self.assertEqual(summary["agreements"], 1)
        self.assertEqual(summary["disagreements"], 2)
        self.assertEqual(summary["tag_counts"]["RULE_SKIP_LLM_STRONG_APPLY"], 1)
        self.assertFalse(summary["rule_score_comparison_available"])


if __name__ == "__main__":
    unittest.main()
