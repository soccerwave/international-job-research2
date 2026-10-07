from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from src.llm.production_shadow import select_production_shadow_inputs

ROOT = Path(__file__).resolve().parents[1]


def _job(job_id: str) -> dict:
    return {
        "canonical_id": job_id,
        "source_record_id": job_id,
        "raw_extra": {},
    }


class LLMProductionShadowWiringTests(unittest.TestCase):
    def test_selection_keeps_main_and_rescue_disjoint_and_uses_current_report_boundaries(self):
        main = _job("main-1")
        rescue = _job("rescue-1")
        excluded = _job("excluded-1")

        def visible(record):
            return record["canonical_id"] != "excluded-1"

        def user_rows(records):
            return [{"recommendation": "APPLY"}] if records[0]["canonical_id"] == "main-1" else []

        def review_rows(records):
            return [{"review_type": "RESCUE_REVIEW"}] if records[0]["canonical_id"] == "rescue-1" else []

        with (
            patch("src.llm.production_shadow._visible_to_control_plane", side_effect=visible),
            patch("src.llm.production_shadow._calibrated_view", side_effect=lambda record: dict(record)),
            patch("src.llm.production_shadow.build_user_rows", side_effect=user_rows),
            patch("src.llm.production_shadow.build_review_rows", side_effect=review_rows),
        ):
            selected = select_production_shadow_inputs([main, rescue, excluded])

        self.assertEqual(selected.main_job_ids, ("main-1",))
        self.assertEqual(selected.rescue_candidate_job_ids, ("rescue-1",))
        self.assertEqual({row["canonical_id"] for row in selected.jobs}, {"main-1", "rescue-1"})
        self.assertFalse(set(selected.main_job_ids) & set(selected.rescue_candidate_job_ids))

    def test_main_precedence_prevents_rescue_reclassification(self):
        main = _job("main-1")
        with (
            patch("src.llm.production_shadow._visible_to_control_plane", return_value=True),
            patch("src.llm.production_shadow._calibrated_view", side_effect=lambda record: dict(record)),
            patch("src.llm.production_shadow.build_user_rows", return_value=[{"recommendation": "REVIEW"}]),
            patch("src.llm.production_shadow.build_review_rows") as review_mock,
        ):
            selected = select_production_shadow_inputs([main])

        self.assertEqual(selected.main_job_ids, ("main-1",))
        self.assertEqual(selected.rescue_candidate_job_ids, ())
        review_mock.assert_not_called()

    def test_existing_publisher_runs_rule_publish_before_non_authoritative_luna_shadow(self):
        workflow = (ROOT / ".github" / "workflows" / "publish-control-plane-report.yml").read_text(encoding="utf-8")
        publish_step = "Publish clean report, audit workbook and latest pointer to international R2"
        shadow_step = "Run GPT-6 Luna shadow experiment"

        self.assertIn(publish_step, workflow)
        self.assertIn(shadow_step, workflow)
        self.assertLess(workflow.index(publish_step), workflow.index(shadow_step))
        shadow_tail = workflow[workflow.index(shadow_step):]
        self.assertIn("continue-on-error: true", shadow_tail)
        self.assertIn("OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}", workflow)
        self.assertIn("LLM_SHADOW_MODEL: gpt-6-luna", workflow)
        self.assertIn("--run-id \"prod-${{ steps.source.outputs.run_id }}-${{ steps.source.outputs.run_attempt }}\"", shadow_tail)
        self.assertIn("retention-days: 21", shadow_tail)
        self.assertIn("Rule production state/report remains authoritative", shadow_tail)


if __name__ == "__main__":
    unittest.main()
