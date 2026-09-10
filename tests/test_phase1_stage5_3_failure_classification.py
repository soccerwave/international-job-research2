from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.runtime.artifacts import write_shard_bundle
from src.runtime.contracts import ShardDiagnostic, ShardStatus
from src.runtime.failure_classification import classify_failure
from src.runtime.observability import collect_run_observability
from src.runtime.production_shards import run_production_shard


class _ResponseError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, error_code: str = "") -> None:
        super().__init__(message)
        metadata = {"HTTPStatusCode": status} if status is not None else {}
        self.response = {"Error": {"Code": error_code}, "ResponseMetadata": metadata}


class Stage53FailureClassificationTests(unittest.TestCase):
    def test_access_denied_is_auth_permission(self):
        exc = _ResponseError("Access Denied", status=403, error_code="AccessDenied")
        self.assertEqual(classify_failure(exc), "AUTH_PERMISSION")

    def test_rate_limit_is_classified(self):
        exc = _ResponseError("Too Many Requests", status=429)
        self.assertEqual(classify_failure(exc), "RATE_LIMIT")

    def test_upstream_5xx_is_classified(self):
        exc = _ResponseError("Service unavailable", status=503)
        self.assertEqual(classify_failure(exc), "UPSTREAM_5XX")

    def test_timeout_is_classified(self):
        self.assertEqual(classify_failure(TimeoutError("collector timed out")), "TIMEOUT")

    def test_unknown_does_not_guess(self):
        self.assertEqual(classify_failure(RuntimeError("unexpected collector failure")), "UNKNOWN")

    def test_source_diagnostic_persists_failure_class(self):
        failing = SimpleNamespace(
            source_id="test_source",
            report_key="test_source",
            collector=lambda: (_ for _ in ()).throw(_ResponseError("Access Denied", error_code="AccessDenied")),
        )
        with tempfile.TemporaryDirectory() as tmp, \
             patch("src.runtime.production_shards.production_specs", return_value={"test-shard": [failing]}):
            diagnostic = run_production_shard(
                run_id="r53",
                shard_id="test-shard",
                output_root=Path(tmp),
            )
            source = diagnostic.metadata["source_results"][0]
            self.assertEqual(source["status"], "ERROR")
            self.assertEqual(source["failure_class"], "AUTH_PERMISSION")

    def test_observability_exposes_failure_class_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            diagnostic = ShardDiagnostic(
                shard_id="test-shard",
                source_ids=["test_source"],
                status=ShardStatus.ERROR,
                started_at="2026-09-10T00:00:00+00:00",
                finished_at="2026-09-10T00:00:01+00:00",
                elapsed_ms=1000,
                records_observed=0,
                records_emitted=0,
                warnings=[],
                errors=["test_source: RuntimeError: denied"],
                metadata={
                    "source_results": [
                        {
                            "source_id": "test_source",
                            "report_key": "test_source",
                            "status": "ERROR",
                            "records": 0,
                            "elapsed_ms": 1000,
                            "warnings": [],
                            "error": "RuntimeError: denied",
                            "failure_class": "AUTH_PERMISSION",
                        }
                    ]
                },
            )
            write_shard_bundle(
                root=root,
                run_id="r53obs",
                shard_id="test-shard",
                source_ids=["test_source"],
                records=[],
                diagnostic=diagnostic,
                producer_version="TEST",
            )
            result = collect_run_observability(
                run_id="r53obs",
                artifact_root=root,
                expected_shards=("test-shard",),
            )
            self.assertEqual(result["failure_class_counts"], {"AUTH_PERMISSION": 1})
            self.assertEqual(result["sources"][0]["failure_classes"], ["AUTH_PERMISSION"])
            self.assertEqual(
                result["sources"][0]["instances"][0]["failure_class"],
                "AUTH_PERMISSION",
            )

    def test_missing_artifact_has_explicit_failure_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = collect_run_observability(
                run_id="missing",
                artifact_root=Path(tmp),
                expected_shards=("missing-shard",),
            )
            self.assertEqual(result["shards"][0]["failure_classes"], ["MISSING_ARTIFACT"])
            self.assertEqual(result["failure_class_counts"], {"MISSING_ARTIFACT": 1})


if __name__ == "__main__":
    unittest.main()
