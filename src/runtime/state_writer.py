from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.state.engine import WRITER_ROLE, apply_state, load_state, save_state_atomic
from src.state.r2_store import R2StateStore


@dataclass(frozen=True)
class StateWriteResult:
    summary: dict[str, Any]
    persistence: dict[str, Any]


class FinalizerStateWriter:
    """The supported durable-state mutation boundary for the central finalizer.

    Stage 8 intentionally does not call this from the Stage 4 raw fan-in finalizer.
    Callers must first reach the canonical/evaluated finalizer record set. Collection
    shards have no state-writer API and never receive R2 state credentials.
    """

    @staticmethod
    def persist_local(
        records: list[dict[str, Any]],
        *,
        state_path: Path,
        observed_at: str,
        run_id: str,
    ) -> StateWriteResult:
        previous = load_state(state_path)
        updated, summary = apply_state(
            records,
            previous,
            observed_at=observed_at,
            run_id=run_id,
            writer_role=WRITER_ROLE,
        )
        save_state_atomic(state_path, updated)
        return StateWriteResult(
            summary=summary,
            persistence={
                "backend": "LOCAL_ATOMIC_FILE",
                "state_path": str(state_path),
                "generation": updated["generation"],
                "state_sha256": summary["state_sha256"],
            },
        )

    @staticmethod
    def persist_r2(
        records: list[dict[str, Any]],
        *,
        store: R2StateStore,
        observed_at: str,
        run_id: str,
        allow_bootstrap: bool = False,
    ) -> StateWriteResult:
        loaded = store.load_current(allow_missing=True)
        if not loaded.exists and not allow_bootstrap:
            raise RuntimeError(
                "Authoritative R2 state is missing. Bootstrap explicitly before the first production state write."
            )
        if not loaded.exists:
            store.bootstrap(loaded.state, run_id=f"{run_id}-bootstrap")
            loaded = store.load_current(allow_missing=False)

        updated, summary = apply_state(
            records,
            loaded.state,
            observed_at=observed_at,
            run_id=run_id,
            writer_role=WRITER_ROLE,
        )
        published = store.publish(updated, expected_etag=loaded.etag, run_id=run_id)
        return StateWriteResult(
            summary=summary,
            persistence={
                "backend": "CLOUDFLARE_R2_CAS",
                **published,
            },
        )
