# V1 Live Bootstrap Repair

Date: 2026-09-05

Status: pending deterministic CI and a new strict live production acceptance.

## Failure observed

The first authoritative production attempt was GitHub Actions run `33925571876` on commit `73ddc0daa2a2dd2ff87365bac1c1178565350f6b`.

It failed in the `readiness` job before collection or state mutation with:

`ModuleNotFoundError: No module named 'jsonschema'`

The production readiness workflow installed only `requirements-cloud.txt`, while `scripts/check_production_state.py` imports `src.runtime.production`, which imports the Stage 10 pre-production module and therefore requires the normal runtime dependency set, including `jsonschema`.

No production shard started and no authoritative R2 state write was reached.

## Root-cause repair

The Stage 8 frozen dependency files remain byte-for-byte unchanged. Instead, every V1 state-facing workflow that imports the production/pre-production runtime now explicitly installs both frozen dependency sets:

`python -m pip install --disable-pip-version-check -r requirements.txt -r requirements-cloud.txt`

This repairs production readiness and the same latent gap in manual recovery without modifying the Stage 8 freeze. V1 CI uses the same install command, so dependency parity is now regression-tested instead of being masked by a different CI setup.

## First-run baseline policy

The original Stage 11 roadmap requires the first complete market inventory to be visible but not reported as today's newly discovered vacancies.

The frozen Stage 8 state engine is not changed. Internally, the first authoritative observation still creates durable identities as `NEW`, which preserves the accepted state semantics and allows the strict bootstrap integrity gate to prove that every canonical vacancy received exactly one state identity.

For production-facing reporting only, a successful fresh bootstrap is rebuilt with the event label:

`BASELINE_EXISTING`

This label is deliberately outside the frozen Stage 9 `CHANGE_EVENTS` set. Therefore the first production workbook and Telegram summary retain the current market inventory while `TODAY_ACTIONABLE` is not flooded by the bootstrap population. From the next run onward, ordinary `NEW`, `SEEN`, `MATERIALLY_CHANGED`, and `REOPENED` semantics apply normally.

## Regression coverage

The V1 repair adds tests proving that:

- production readiness, recovery, and V1 CI install both frozen dependency sets with the same command
- baseline conversion does not mutate the internal canonical/state record set
- `BASELINE_EXISTING` is not a Stage 9 change event
- an actionable bootstrap vacancy remains in `CURRENT_ACTIONABLE` while being excluded from `TODAY_ACTIONABLE`
- the production finalizer applies the baseline report rebuild only after a successful fresh bootstrap

No Stage 7, Stage 8, Stage 9, or Stage 10 protected behavior file is modified by this repair.
