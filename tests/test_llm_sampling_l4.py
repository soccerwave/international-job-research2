from __future__ import annotations

import unittest

from src.llm.sampling import SamplingConfig, sampling_summary, select_shadow_sample


def job(
    idx: int,
    recommendation: str,
    *,
    country: str = "DE",
    source: str = "source_a",
    detail_status: str = "FULL",
    scientific: str = "WEAK",
    review_codes: list[str] | None = None,
    blocker_codes: list[str] | None = None,
    role_policy_status: str = "OUT_OF_SCOPE",
) -> dict:
    return {
        "canonical_id": f"job-{idx}",
        "source_record_id": f"source:{idx}",
        "source": {"source_key": source},
        "location": {"country_code": country},
        "description": {
            "detail_status": detail_status,
            "full_jd": f"Full vacancy text for job {idx}." if detail_status in {"FULL", "PARTIAL"} else "",
        },
        "raw_extra": {
            "evaluation": {
                "evaluator_version": "E0.1",
                "recommendation": recommendation,
                "role_policy_status": role_policy_status,
                "dimensions": {"scientific": scientific, "level": "UNKNOWN", "methods": "UNKNOWN"},
                "review_codes": list(review_codes or []),
                "blocker_codes": list(blocker_codes or []),
                "fit_signals": ["must never become LLM prompt context"],
                "reason": "rule reason must remain sampling-only",
            }
        },
    }


class LLMSamplingL4Tests(unittest.TestCase):
    def test_all_positive_jobs_are_selected_even_above_nominal_targets(self):
        rows = [job(i, "APPLY") for i in range(20)] + [job(100 + i, "SKIP") for i in range(20)]
        sample = select_shadow_sample(
            rows,
            seed="2026-10-06",
            config=SamplingConfig(review_target=0, negative_target=5),
        )
        positive_ids = {row.job["canonical_id"] for row in sample if row.sampling_bucket == "ALL_POSITIVE"}
        self.assertEqual(len(positive_ids), 20)
        self.assertTrue({f"job-{i}" for i in range(20)}.issubset(positive_ids))

    def test_review_more_has_priority_then_e01_review_fills_remaining_quota(self):
        review_more = [job(i, "SKIP", country="DE", source="rm") for i in range(5)]
        reviews = [job(100 + i, "REVIEW", country="NL", source="review") for i in range(10)]
        ids = {row["canonical_id"] for row in review_more}
        sample = select_shadow_sample(
            review_more + reviews,
            seed="day-1",
            config=SamplingConfig(review_target=8, negative_target=0),
            review_more_job_ids=ids,
        )
        buckets = [row.sampling_bucket for row in sample]
        self.assertEqual(buckets.count("REVIEW_MORE_STRATIFIED"), 5)
        self.assertEqual(buckets.count("E01_REVIEW_FILL"), 3)

    def test_review_more_is_not_treated_as_an_e01_recommendation(self):
        rows = [job(1, "SKIP"), job(2, "REVIEW")]
        sample_without_external_marker = select_shadow_sample(
            rows,
            seed="day-1",
            config=SamplingConfig(review_target=1, negative_target=0),
        )
        self.assertEqual(sample_without_external_marker[0].job["canonical_id"], "job-2")
        self.assertEqual(sample_without_external_marker[0].sampling_bucket, "E01_REVIEW_FILL")

    def test_negative_sample_contains_targeted_and_blind_exploration(self):
        targeted = [
            job(i, "SKIP", scientific="ADJACENT", role_policy_status="AMBIGUOUS", source=f"targeted_{i % 2}")
            for i in range(20)
        ]
        blind = [
            job(100 + i, "SKIP", scientific="WEAK", role_policy_status="OUT_OF_SCOPE", source=f"blind_{i % 2}")
            for i in range(20)
        ]
        sample = select_shadow_sample(
            targeted + blind,
            seed="day-2",
            config=SamplingConfig(review_target=0, negative_target=10, targeted_negative_fraction=0.5),
        )
        buckets = [row.sampling_bucket for row in sample]
        self.assertEqual(buckets.count("NEGATIVE_TARGETED"), 5)
        self.assertEqual(buckets.count("NEGATIVE_BLIND_EXPLORATION"), 5)

    def test_negative_quota_backfills_when_targeted_pool_is_too_small(self):
        targeted = [job(1, "SKIP", scientific="ADJACENT", role_policy_status="AMBIGUOUS")]
        blind = [job(100 + i, "SKIP", scientific="WEAK", role_policy_status="OUT_OF_SCOPE") for i in range(20)]
        sample = select_shadow_sample(
            targeted + blind,
            seed="day-3",
            config=SamplingConfig(review_target=0, negative_target=10, targeted_negative_fraction=0.8),
        )
        negative = [row for row in sample if row.sampling_bucket.startswith("NEGATIVE_")]
        self.assertEqual(len(negative), 10)
        self.assertTrue(any(row.sampling_bucket == "NEGATIVE_BACKFILL" for row in negative))

    def test_blind_exploration_excludes_unavailable_detail(self):
        rows = [
            job(1, "SKIP", detail_status="UNAVAILABLE"),
            job(2, "SKIP", detail_status="FULL"),
        ]
        sample = select_shadow_sample(
            rows,
            seed="day-4",
            config=SamplingConfig(review_target=0, negative_target=2, targeted_negative_fraction=0.0),
        )
        ids = {row.job["canonical_id"] for row in sample}
        self.assertNotIn("job-1", ids)
        self.assertIn("job-2", ids)

    def test_sampling_is_deterministic_for_same_seed_and_changes_with_seed(self):
        rows = [
            job(i, "REVIEW", country=("DE" if i % 2 else "NL"), source=f"source_{i % 3}")
            for i in range(50)
        ]
        config = SamplingConfig(review_target=10, negative_target=0)
        a = select_shadow_sample(rows, seed="2026-10-06", config=config)
        b = select_shadow_sample(rows, seed="2026-10-06", config=config)
        c = select_shadow_sample(rows, seed="2026-10-07", config=config)
        ids_a = [row.job["canonical_id"] for row in a]
        ids_b = [row.job["canonical_id"] for row in b]
        ids_c = [row.job["canonical_id"] for row in c]
        self.assertEqual(ids_a, ids_b)
        self.assertNotEqual(ids_a, ids_c)

    def test_sampling_stratifies_across_country_and_source(self):
        rows = []
        idx = 0
        for country, source in (("DE", "a"), ("DE", "b"), ("NL", "a"), ("BE", "c")):
            for _ in range(10):
                rows.append(job(idx, "REVIEW", country=country, source=source))
                idx += 1
        sample = select_shadow_sample(
            rows,
            seed="stratified",
            config=SamplingConfig(review_target=4, negative_target=0),
        )
        strata = {(row.job["location"]["country_code"], row.job["source"]["source_key"]) for row in sample}
        self.assertEqual(len(strata), 4)

    def test_duplicate_canonical_jobs_are_not_sampled_twice(self):
        duplicate = job(1, "APPLY")
        sample = select_shadow_sample(
            [duplicate, duplicate, job(2, "REVIEW")],
            seed="dedupe",
            config=SamplingConfig(review_target=10, negative_target=0),
        )
        ids = [row.job["canonical_id"] for row in sample]
        self.assertEqual(ids.count("job-1"), 1)

    def test_summary_keeps_rule_recommendation_as_sampling_metadata_only(self):
        sample = select_shadow_sample(
            [job(1, "APPLY"), job(2, "REVIEW"), job(3, "SKIP")],
            seed="summary",
            config=SamplingConfig(review_target=1, negative_target=1, targeted_negative_fraction=0.0),
        )
        summary = sampling_summary(sample)
        self.assertEqual(summary["selected"], 3)
        self.assertEqual(summary["by_rule_recommendation"]["APPLY"], 1)
        self.assertEqual(summary["by_rule_recommendation"]["REVIEW"], 1)
        self.assertEqual(summary["by_rule_recommendation"]["SKIP"], 1)


if __name__ == "__main__":
    unittest.main()
