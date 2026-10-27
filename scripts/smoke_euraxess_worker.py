"""Manual isolated transport smoke. Never writes R2 state or changes production."""
from __future__ import annotations

import json
from src.sources.shared import euraxess
from src.sources.shared.euraxess_worker_transport import configured_session


def main():
    session = configured_session()
    if session is None:
        raise RuntimeError("EURAXESS Worker configuration is missing")
    rows = euraxess.collect(
        country_codes=("DE",),
        pages_per_country=2,
        max_jobs=15,
        enrich_detail=False,
        session=session,
        pace_seconds=0,
    )
    failures = [
        {"id":r.get("source_job_id"),"country":r.get("country")}
        for r in rows
        if r.get("location", {}).get("country_code") not in (None, "DE")
    ]
    print(json.dumps({"rows":len(rows),"country_mismatches":failures,
                      "success":len(rows)>0 and not failures},sort_keys=True))
    if not rows or failures:
        raise SystemExit("EURAXESS Worker smoke failed")


if __name__ == "__main__":
    main()
