from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from src.llm.evaluation_cache import append_cache_record, build_cache_fingerprint, load_successful_cache
from src.llm.shadow_evaluator import LLMResponse

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_SCHEMA_PATH = ROOT / "schemas" / "llm_rescue_triage.schema.json"
TRIAGE_SCHEMA_VERSION = "LLM_RESCUE_TRIAGE_V0.1"

PASS_TO_FULL_REVIEW = "PASS_TO_FULL_REVIEW"
CLEARLY_OUT_OF_SCOPE = "CLEARLY_OUT_OF_SCOPE"


class RescueTriageError(RuntimeError):
    pass


class LLMTransport(Protocol):
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
    ) -> LLMResponse:
        ...


@dataclass(frozen=True)
class RescueTriageInput:
    triage_id: str
    job_id: str
    metadata: dict[str, Any]
    candidate_summary: dict[str, Any]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _job_id(job: dict[str, Any]) -> str:
    return str(job.get("canonical_id") or job.get("source_record_id") or "").strip()


def _source_url(job: dict[str, Any]) -> str | None:
    source = job.get("source") or {}
    return source.get("detail_url") or source.get("listing_url") or source.get("apply_url")


def _location_text(job: dict[str, Any]) -> str:
    loc = job.get("location") or {}
    parts = [loc.get("city"), loc.get("region"), loc.get("country_name") or loc.get("country_code")]
    return ", ".join(_clean(x) for x in parts if _clean(x))


def _candidate_summary(profile: dict[str, Any]) -> dict[str, Any]:
    evidence = profile.get("evidence_profile") or {}
    career = evidence.get("career_stage") or {}
    education = evidence.get("education") or []
    preferences = profile.get("search_preferences") or {}
    return {
        "profile_version": str(profile.get("profile_version") or "").strip(),
        "career_stage": {
            "current_level": career.get("current_level"),
            "summary": career.get("summary"),
        },
        "degrees": [
            {"degree": row.get("degree"), "field": row.get("field")}
            for row in education
            if isinstance(row, dict)
        ],
        "target_role_families": list(preferences.get("target_role_families") or []),
        "core_domains": list(preferences.get("core_domains") or []),
        "adjacent_domains": list(preferences.get("adjacent_domains") or []),
    }


def build_rescue_triage_input(
    canonical_job: dict[str, Any],
    candidate_profile: dict[str, Any],
) -> RescueTriageInput:
    job_id = _job_id(canonical_job)
    if not job_id:
        raise RescueTriageError("canonical job has no stable identifier")

    candidate_summary = _candidate_summary(candidate_profile)
    if not candidate_summary["profile_version"]:
        raise RescueTriageError("candidate profile has no profile_version")

    position = canonical_job.get("position") or {}
    location = canonical_job.get("location") or {}
    contract = canonical_job.get("contract") or {}
    raw_extra = canonical_job.get("raw_extra") or {}

    metadata = {
        "title": _clean(position.get("title_raw") or position.get("title_normalized")),
        "institution": _clean(position.get("institution_raw") or position.get("institution_normalized")),
        "department": _clean(position.get("department") or raw_extra.get("department")),
        "location": _location_text(canonical_job),
        "country": location.get("country_name") or location.get("country_code"),
        "role_family": position.get("role_family"),
        "role_level": position.get("role_level"),
        "employment_type": position.get("employment_type"),
        "contract_type": contract.get("term_type"),
        "source_url": _source_url(canonical_job),
    }

    fingerprint_material = json.dumps(
        {
            "job_id": job_id,
            "metadata": metadata,
            "candidate_profile_version": candidate_summary["profile_version"],
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    triage_id = hashlib.sha256(fingerprint_material).hexdigest()[:24]
    return RescueTriageInput(
        triage_id=triage_id,
        job_id=job_id,
        metadata=metadata,
        candidate_summary=candidate_summary,
    )


def _system_prompt() -> str:
    return (
        "You are a recall-first routing triage for academic and research vacancies. "
        "Your only job is to decide whether a vacancy is so clearly outside this candidate's target scope "
        "that it does not justify reading the full job description. "
        "Do not judge final fit, eligibility, methods fit, or application strength at this stage. "
        "If the title or metadata are generic, interdisciplinary, incomplete, ambiguous, or plausibly connected "
        "to the candidate's target role families, core domains, adjacent domains, or transferable research profile, "
        "return PASS_TO_FULL_REVIEW. "
        "Use CLEARLY_OUT_OF_SCOPE only when the occupational/scientific mismatch is obvious from the limited metadata. "
        "Examples that should usually pass include generic postdoctoral or research roles in health, psychology, "
        "neuroscience, physiology, rehabilitation, ageing, behavior, lifestyle, digital health, human performance, "
        "or other potentially adjacent research areas. "
        "Do not reject merely because exact exercise-related keywords are absent. "
        "When uncertain, always return PASS_TO_FULL_REVIEW. "
        "Return only one JSON object conforming exactly to the supplied schema."
    )


def _user_prompt(triage_input: RescueTriageInput) -> str:
    return json.dumps(
        {
            "task": "Route this Rescue candidate using metadata only. Do not infer unseen full-JD content.",
            "vacancy_metadata": triage_input.metadata,
            "candidate_summary": triage_input.candidate_summary,
            "decision_definitions": {
                PASS_TO_FULL_REVIEW: (
                    "Any plausible, ambiguous, generic, interdisciplinary, adjacent, or potentially transferable "
                    "academic/research vacancy that deserves a full-JD read."
                ),
                CLEARLY_OUT_OF_SCOPE: (
                    "Only an obviously unrelated occupation or scientific area where the limited metadata already "
                    "makes relevance implausible."
                ),
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _transport_identity(transport: LLMTransport) -> str:
    explicit = getattr(transport, "cache_identity", None)
    if callable(explicit):
        explicit = explicit()
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    cls = type(transport)
    return f"{cls.__module__}.{cls.__qualname__}"


def _load_schema() -> dict[str, Any]:
    return json.loads(OUTPUT_SCHEMA_PATH.read_text(encoding="utf-8"))


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RescueTriageError(f"malformed triage JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise RescueTriageError("triage response must be a JSON object")
    return parsed


def _validate_output(result: dict[str, Any], triage_id: str) -> dict[str, Any]:
    row = dict(result)
    row.setdefault("schema_version", TRIAGE_SCHEMA_VERSION)
    row.setdefault("triage_id", triage_id)
    if row.get("triage_id") != triage_id:
        raise RescueTriageError("triage response triage_id does not match request")
    validator = Draft202012Validator(_load_schema())
    errors = sorted(validator.iter_errors(row), key=lambda e: list(e.path))
    if errors:
        raise RescueTriageError("invalid triage output: " + "; ".join(e.message for e in errors))
    return row


class RescueTriageEvaluator:
    def __init__(
        self,
        *,
        transport: LLMTransport,
        candidate_profile: dict[str, Any],
        cache_path: Path | None = None,
    ) -> None:
        self.transport = transport
        self.candidate_profile = candidate_profile
        self.cache_path = cache_path
        self._cache = load_successful_cache(cache_path)

    def evaluate(self, canonical_job: dict[str, Any]) -> dict[str, Any]:
        triage_input = build_rescue_triage_input(canonical_job, self.candidate_profile)
        system_prompt = _system_prompt()
        user_prompt = _user_prompt(triage_input)
        output_schema = _load_schema()
        cache_fingerprint = build_cache_fingerprint(
            llm_input={
                "schema_version": "LLM_RESCUE_TRIAGE_INPUT_V0.1",
                "triage_id": triage_input.triage_id,
                "job": triage_input.metadata,
            },
            candidate_profile=triage_input.candidate_summary,
            system_prompt=system_prompt,
            output_schema=output_schema,
            transport_identity=_transport_identity(self.transport),
        )

        cached = self._cache.get(cache_fingerprint)
        if cached is not None:
            reused = copy.deepcopy(cached)
            reused["cache_hit"] = True
            reused["cache_reused_at"] = datetime.now(timezone.utc).isoformat()
            return reused

        try:
            response = self.transport.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=output_schema,
            )
        except Exception as exc:
            raise RescueTriageError(f"triage transport failed: {type(exc).__name__}: {exc}") from exc

        result = _validate_output(_extract_json(response.text), triage_input.triage_id)
        record = {
            "shadow_schema_version": "LLM_RESCUE_TRIAGE_RESULT_V0.1",
            "evaluation_kind": "RESCUE_TRIAGE",
            "triage_id": triage_input.triage_id,
            "job_id": triage_input.job_id,
            "candidate_profile_version": triage_input.candidate_summary["profile_version"],
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "cache_fingerprint": cache_fingerprint,
            "cache_hit": False,
            "llm_result": result,
        }
        append_cache_record(self.cache_path, record)
        self._cache[cache_fingerprint] = record
        return record
