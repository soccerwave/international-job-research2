import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from src.state.engine import (
    STATE_VERSION,
    WRITER_ROLE,
    apply_state,
    empty_state,
    load_state,
    save_state_atomic,
)

ROOT = Path(__file__).resolve().parents[1]
STATE_SCHEMA = json.loads((ROOT / "schemas" / "state.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(STATE_SCHEMA)


def job(job_id="1", *, status="OPEN", detail_status="FULL", title="Postdoctoral Researcher in Exercise Physiology"):
    jd = (
        "This postdoctoral research project studies exercise physiology, physical activity, fitness, "
        "human exercise interventions, cognition, stress biology and psychological health. "
        "The successful candidate will contribute to randomized controlled trials, physiological "
        "assessment, statistical analysis and international research collaboration. "
    ) * 2
    if detail_status not in {"FULL", "PARTIAL"}:
        jd = None
    return {
        "schema_version": "VACANCY_SCHEMA_V1.0.0",
        "record_stage": "SHARD_ENRICHED",
        "source_record_id": f"fixture:{job_id}",
        "canonical_id": None,
        "source": {
            "source_key": "fixture",
            "source_kind": "DIRECT_INSTITUTION",
            "provider": "Fixture University",
            "source_job_id": str(job_id),
            "listing_url": f"https://example.org/jobs/{job_id}",
            "detail_url": f"https://example.org/jobs/{job_id}",
            "apply_url": f"https://example.org/jobs/{job_id}/apply",
            "retrieved_at": "2026-09-04T12:00:00Z",
            "source_language": "en",
            "source_status": status,
        },
        "position": {
            "title_raw": title,
            "title_normalized": None,
            "institution_raw": "Fixture University",
            "institution_normalized": None,
            "department": "Exercise Science",
            "role_family": "POSTDOC",
            "role_level": "POSTDOC",
            "employment_type": "FULL_TIME",
            "workplace_mode": "ONSITE",
        },
        "location": {"country_code": "NL", "country_name": "Netherlands", "city": "Amsterdam", "region": None},
        "dates": {
            "posted_at": None,
            "deadline_at": "2026-10-01T23:59:00Z",
            "deadline_text": "1 October 2026",
            "deadline_status": "KNOWN",
            "collected_at": "2026-09-04T12:00:00Z",
        },
        "contract": {
            "term_type": "FIXED_TERM",
            "duration_months": 24,
            "fte": 1.0,
            "salary": {"min": None, "max": None, "currency": "EUR", "period": "YEAR", "raw_text": None},
        },
        "description": {
            "full_jd": jd,
            "detail_status": detail_status,
            "detail_failure_reason": None if jd else "temporary fetch failure",
            "detail_retrieved_at": "2026-09-04T12:00:00Z" if jd else None,
        },
        "requirements": {
            "phd_requirement": "REQUIRED",
            "degree_text": "PhD in exercise physiology or related field",
            "degree_fields": ["exercise physiology"],
            "years_postdoc": None,
            "language_requirements": [],
            "work_rights_text": None,
            "sponsorship_text": None,
            "professional_registration_text": None,
            "teaching_requirement_text": None,
            "methods_required": [],
            "methods_preferred": [],
        },
        "classification": {
            "market_tier": "CORE",
            "role_policy_status": "PRIMARY",
            "pre_evaluation_disposition": "ELIGIBLE_FOR_EVALUATION",
            "review_codes": [],
            "blocker_codes": [],
        },
        "provenance": {"observed_by_sources": ["fixture"], "raw_payload_fingerprint": None, "notes": []},
        "raw_extra": {},
    }


def apply(records, state=None, run="run-1", observed="2026-09-04T12:00:00Z"):
    return apply_state(records, state, observed_at=observed, run_id=run, writer_role=WRITER_ROLE)


class Stage8StateTests(unittest.TestCase):
    def assert_schema(self, state):
        errors = list(VALIDATOR.iter_errors(state))
        self.assertFalse(errors, "; ".join(e.message for e in errors))

    def test_empty_state_contract(self):
        state = empty_state()
        self.assertEqual(state["state_version"], STATE_VERSION)
        self.assertEqual(state["generation"], 0)
        self.assertEqual(state["writer_role"], WRITER_ROLE)
        self.assert_schema(state)

    def test_first_observation_is_new(self):
        row = job()
        state, summary = apply([row])
        self.assertEqual(summary["NEW"], 1)
        self.assertEqual(row["raw_extra"]["state"]["seen_status"], "NEW")
        self.assertEqual(state["generation"], 1)
        self.assert_schema(state)

    def test_second_observation_is_seen(self):
        first = job()
        state, _ = apply([first])
        second = job()
        state2, summary = apply([second], state, run="run-2", observed="2026-09-05T12:00:00Z")
        self.assertEqual(summary["SEEN"], 1)
        self.assertEqual(second["raw_extra"]["state"]["times_seen"], 2)
        self.assertEqual(len(state2["jobs"]), 1)

    def test_source_id_preserves_identity_when_url_changes(self):
        first = job()
        state, _ = apply([first])
        second = job()
        second["source"]["listing_url"] = "https://new.example.org/recruitment/vacancy/1"
        second["source"]["detail_url"] = second["source"]["listing_url"]
        state2, summary = apply([second], state, run="run-2", observed="2026-09-05T12:00:00Z")
        self.assertEqual(summary["SEEN"], 1)
        self.assertEqual(len(state2["jobs"]), 1)

    def test_deadline_change_is_material(self):
        state, _ = apply([job()])
        changed = job()
        changed["dates"]["deadline_at"] = "2026-10-15T23:59:00Z"
        _, summary = apply([changed], state, run="run-2", observed="2026-09-05T12:00:00Z")
        self.assertEqual(summary["MATERIALLY_CHANGED"], 1)
        self.assertIn("deadline_at", changed["raw_extra"]["state"]["change_reasons"])

    def test_detail_degradation_is_quality_event_not_material_change(self):
        state, _ = apply([job()])
        degraded = job(detail_status="FETCH_FAILED")
        state2, summary = apply([degraded], state, run="run-2", observed="2026-09-05T12:00:00Z")
        self.assertEqual(summary["SEEN"], 1)
        self.assertEqual(summary["DETAIL_UNRESOLVED"], 1)
        entry = next(iter(state2["jobs"].values()))
        self.assertEqual(entry["last_snapshot"]["detail_status"], "FULL")

    def test_detail_recovery_is_quality_event_not_material_change(self):
        first = job(detail_status="FETCH_FAILED")
        state, _ = apply([first])
        recovered = job()
        _, summary = apply([recovered], state, run="run-2", observed="2026-09-05T12:00:00Z")
        self.assertEqual(summary["SEEN"], 1)
        self.assertEqual(summary["DETAIL_RESOLVED"], 1)

    def test_material_full_jd_rewrite_is_changed(self):
        state, _ = apply([job()])
        changed = job()
        changed["description"]["full_jd"] = (
            "A completely revised vacancy now focuses on field experiments, teaching design, public engagement, "
            "participant recruitment, longitudinal cohort management, wearable sensor deployment and intervention delivery. "
        ) * 5
        _, summary = apply([changed], state, run="run-2", observed="2026-09-05T12:00:00Z")
        self.assertEqual(summary["MATERIALLY_CHANGED"], 1)
        self.assertIn("full_jd", changed["raw_extra"]["state"]["change_reasons"])

    def test_explicit_closed_then_open_is_reopened(self):
        closed = job(status="CLOSED")
        state, _ = apply([closed])
        reopened = job(status="OPEN")
        _, summary = apply([reopened], state, run="run-2", observed="2026-09-05T12:00:00Z")
        self.assertEqual(summary["REOPENED"], 1)
        self.assertEqual(reopened["raw_extra"]["state"]["seen_status"], "REOPENED")

    def test_unknown_status_does_not_fake_reopen(self):
        state, _ = apply([job(status="CLOSED")])
        unknown = job(status="UNKNOWN")
        _, summary = apply([unknown], state, run="run-2", observed="2026-09-05T12:00:00Z")
        self.assertEqual(summary["REOPENED"], 0)
        self.assertEqual(summary["MATERIALLY_CHANGED"], 1)

    def test_absence_never_infers_closure(self):
        state, _ = apply([job("1"), job("2")])
        state2, summary = apply([job("1")], state, run="run-2", observed="2026-09-05T12:00:00Z")
        self.assertEqual(summary["not_observed_inferred_closed"], 0)
        self.assertEqual(len(state2["jobs"]), 2)
        second = [e for e in state2["jobs"].values() if any("source_id:fixture:2" == a for a in e["aliases"])][0]
        self.assertEqual(second["last_seen_at"], "2026-09-04T12:00:00Z")
        self.assertEqual(second["lifecycle_status"], "OPEN")

    def test_generic_listing_url_does_not_merge_distinct_source_ids(self):
        one = job("1", title="Research Fellow")
        two = job("2", title="Research Fellow")
        for record in (one, two):
            record["source"]["listing_url"] = "https://example.org/jobs"
            record["source"]["detail_url"] = None
            record["source"]["apply_url"] = None
        state, summary = apply([one, two])
        self.assertEqual(summary["NEW"], 2)
        self.assertEqual(len(state["jobs"]), 2)

    def test_non_finalizer_writer_is_rejected(self):
        with self.assertRaises(PermissionError):
            apply_state([job()], empty_state(), observed_at="2026-09-04T12:00:00Z", run_id="bad", writer_role="SHARD")

    def test_input_state_is_not_mutated(self):
        state, _ = apply([job()])
        before = deepcopy(state)
        apply([job()], state, run="run-2", observed="2026-09-05T12:00:00Z")
        self.assertEqual(state, before)

    def test_atomic_save_and_reload(self):
        state, _ = apply([job()])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            save_state_atomic(path, state)
            loaded = load_state(path)
            self.assertEqual(loaded, state)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_corrupt_state_is_rejected_not_reseeded(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                load_state(path)

    def test_identity_conflict_is_rejected(self):
        one = job("1")
        two = job("2")
        state, _ = apply([one, two])
        merged = job("1")
        merged["canonical_id"] = "canonical-x"
        # First associate canonical alias with source 1.
        state, _ = apply([merged], state, run="run-2", observed="2026-09-05T12:00:00Z")
        conflict = job("2")
        conflict["canonical_id"] = "canonical-x"
        with self.assertRaises(RuntimeError):
            apply([conflict], state, run="run-3", observed="2026-09-06T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
