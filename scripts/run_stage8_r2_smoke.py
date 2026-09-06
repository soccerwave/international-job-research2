from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.state.engine import WRITER_ROLE, apply_state, empty_state
from src.state.r2_store import R2StateStore, StateConflict


def record() -> dict:
    return {
        "schema_version": "VACANCY_SCHEMA_V1.0.0",
        "record_stage": "SHARD_ENRICHED",
        "source_record_id": "stage8-live:1",
        "canonical_id": None,
        "source": {
            "source_key":"stage8_live",
            "source_job_id":"1",
            "listing_url":"https://example.invalid/jobs/1",
            "detail_url":"https://example.invalid/jobs/1",
            "apply_url":None,
            "source_status":"OPEN",
        },
        "position": {
            "title_raw":"Postdoctoral Researcher in Exercise Physiology",
            "institution_raw":"Stage 8 Validation University",
            "department":"Exercise Science",
            "role_family":"POSTDOC",
            "role_level":"POSTDOC",
            "employment_type":"FULL_TIME",
            "workplace_mode":"ONSITE",
        },
        "location":{"country_code":"NL","city":"Amsterdam"},
        "dates":{"deadline_at":None,"deadline_status":"UNKNOWN"},
        "contract":{"term_type":"FIXED_TERM","duration_months":24,"fte":1.0},
        "description":{
            "full_jd":"exercise physiology physical activity fitness intervention research cognition stress biology " * 10,
            "detail_status":"FULL",
        },
        "raw_extra":{},
    }


def main() -> int:
    run_id = str(os.environ.get("GITHUB_RUN_ID") or "local") + "-" + str(os.environ.get("GITHUB_RUN_ATTEMPT") or "1")
    prefix = f"acceptance/stage8/{run_id}"
    store = R2StateStore.from_env(prefix=prefix)

    initial = store.load_current()
    if initial.exists:
        raise RuntimeError(f"Acceptance prefix unexpectedly already exists: {prefix}")

    bootstrap = store.bootstrap(empty_state(), run_id=f"{run_id}-bootstrap")
    loaded0 = store.load_current(allow_missing=False)

    row1 = record()
    state1, summary1 = apply_state(
        [row1], loaded0.state,
        observed_at="2026-09-04T18:30:00Z",
        run_id=f"{run_id}-g1",
        writer_role=WRITER_ROLE,
    )
    publish1 = store.publish(state1, expected_etag=loaded0.etag, run_id=f"{run_id}-g1")
    loaded1 = store.load_current(allow_missing=False)

    row2 = record()
    state2, summary2 = apply_state(
        [row2], loaded1.state,
        observed_at="2026-09-04T18:31:00Z",
        run_id=f"{run_id}-g2",
        writer_role=WRITER_ROLE,
    )
    publish2 = store.publish(state2, expected_etag=loaded1.etag, run_id=f"{run_id}-g2")

    stale_conflict = False
    stale_state, _ = apply_state(
        [record()], loaded0.state,
        observed_at="2026-09-04T18:32:00Z",
        run_id=f"{run_id}-stale",
        writer_role=WRITER_ROLE,
    )
    try:
        store.publish(stale_state, expected_etag=loaded0.etag, run_id=f"{run_id}-stale")
    except StateConflict:
        stale_conflict = True
    if not stale_conflict:
        raise RuntimeError("Stale R2 writer was not rejected")

    final = store.load_current(allow_missing=False)
    if final.state["generation"] != 2 or len(final.state["jobs"]) != 1:
        raise RuntimeError(f"Unexpected final state: generation={final.state['generation']} jobs={len(final.state['jobs'])}")
    if summary1["NEW"] != 1 or summary2["SEEN"] != 1:
        raise RuntimeError(f"Unexpected state events: {summary1} / {summary2}")

    result = {
        "status":"PASS",
        "validation_profile":"STAGE8_R2_LIVE_CAS",
        "prefix":prefix,
        "bucket":str(os.environ.get("R2_BUCKET") or ""),
        "bootstrap":bootstrap,
        "publish_generation_1":publish1,
        "publish_generation_2":publish2,
        "stale_writer_rejected":stale_conflict,
        "final_generation":final.state["generation"],
        "final_jobs":len(final.state["jobs"]),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
