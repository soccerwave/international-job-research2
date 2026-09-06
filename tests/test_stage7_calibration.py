import json
import unittest
from pathlib import Path

from src.evaluation import evaluate_vacancy
from tests.test_stage7_evaluator import base_job

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests" / "fixtures" / "stage7_calibration_cases.json").read_text(encoding="utf-8"))


class Stage7CalibrationTests(unittest.TestCase):
    def test_cross_market_calibration_matrix(self):
        failures = []
        distribution = {}
        for case in CASES:
            job = base_job(title=case["title"], country=case["country"], jd=case.get("jd"))
            if case.get("detail_status"):
                job["description"]["detail_status"] = case["detail_status"]
                if case["detail_status"] not in {"FULL", "PARTIAL"}:
                    job["description"]["detail_retrieved_at"] = None
            if "sponsorship" in case:
                job["requirements"]["sponsorship_text"] = case["sponsorship"]
            if "employment_type" in case:
                job["position"]["employment_type"] = case["employment_type"]
            if "phd_requirement" in case:
                job["requirements"]["phd_requirement"] = case["phd_requirement"]
            if "degree_text" in case:
                job["requirements"]["degree_text"] = case["degree_text"]
            if "degree_fields" in case:
                job["requirements"]["degree_fields"] = case["degree_fields"]

            result = evaluate_vacancy(job)
            got = result["recommendation"]
            distribution[got] = distribution.get(got, 0) + 1
            if got != case["expected"]:
                failures.append(
                    f"{case['id']}: expected {case['expected']}, got {got}; "
                    f"dims={result['dimensions']} reviews={result['review_codes']} blockers={result['blocker_codes']}"
                )

        self.assertFalse(failures, "\n".join(failures))
        self.assertGreaterEqual(distribution.get("STRONG_APPLY", 0), 4)
        self.assertGreaterEqual(distribution.get("APPLY", 0), 2)
        self.assertGreaterEqual(distribution.get("REVIEW", 0), 4)
        self.assertGreaterEqual(distribution.get("LOW_PRIORITY", 0), 1)
        self.assertGreaterEqual(distribution.get("SKIP", 0), 1)


if __name__ == "__main__":
    unittest.main()
