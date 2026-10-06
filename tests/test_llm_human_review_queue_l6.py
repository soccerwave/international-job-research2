import unittest

from src.llm.human_review_queue import apply_human_label, build_human_review_queue


class HumanReviewQueueL6Tests(unittest.TestCase):
    def test_false_negative_candidates_are_prioritized(self):
        rows = [
            {
                "job_id": "a", "evaluation_id": "e1", "is_disagreement": True,
                "rule_recommendation": "SKIP", "llm_decision": "STRONG_APPLY",
                "llm_fit_score": 91, "llm_confidence": 88, "evidence_quality": "FULL_JD",
                "decision_distance": 4, "direction": "LLM_UPRANK",
                "disagreement_tags": ["RULE_SKIP_LLM_STRONG_APPLY", "DECISION_DISTANCE_GE_2", "LLM_UPRANK"],
            },
            {
                "job_id": "b", "evaluation_id": "e2", "is_disagreement": True,
                "rule_recommendation": "APPLY", "llm_decision": "SKIP",
                "llm_fit_score": 20, "llm_confidence": 80, "evidence_quality": "FULL_JD",
                "decision_distance": -3, "direction": "LLM_DOWNRANK",
                "disagreement_tags": ["RULE_APPLY_LLM_SKIP", "DECISION_DISTANCE_GE_2", "LLM_DOWNRANK"],
            },
        ]
        queue = build_human_review_queue(rows)
        self.assertEqual([x["job_id"] for x in queue], ["a", "b"])
        self.assertTrue(queue[0]["false_negative_candidate"])
        self.assertFalse(queue[1]["false_negative_candidate"])
        self.assertIsNone(queue[0]["human_label"])

    def test_agreements_are_not_queued(self):
        rows = [{
            "job_id": "a", "evaluation_id": "e1", "is_disagreement": False,
            "rule_recommendation": "APPLY", "llm_decision": "APPLY",
            "llm_fit_score": 80, "llm_confidence": 90, "evidence_quality": "FULL_JD",
            "decision_distance": 0, "direction": "AGREEMENT", "disagreement_tags": [],
        }]
        self.assertEqual(build_human_review_queue(rows), [])

    def test_labels_match_roadmap_and_invalid_label_is_rejected(self):
        item = {"job_id": "a", "human_label": None, "human_notes": None}
        updated = apply_human_label(item, "LLM_CORRECT", "semantic fit visible in full JD")
        self.assertEqual(updated["human_label"], "LLM_CORRECT")
        self.assertIsNone(item["human_label"])
        with self.assertRaises(ValueError):
            apply_human_label(item, "AUTO_PROMOTE")


if __name__ == "__main__":
    unittest.main()
