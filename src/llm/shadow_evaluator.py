from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from src.llm.context_quality import ContextQualityResult, clean_vacancy_text, prepare_vacancy_context
from src.llm.evaluation_cache import append_cache_record, build_cache_fingerprint, load_successful_cache

ROOT = Path(__file__).resolve().parents[2]
INPUT_SCHEMA_PATH = ROOT / "schemas" / "llm_evaluator_input.schema.json"
OUTPUT_SCHEMA_PATH = ROOT / "schemas" / "llm_evaluation.schema.json"
DEFAULT_MAX_CONTEXT_CHARS = 120_000

PROHIBITED_INPUT_KEYS = {
    "rule_based_decision",
    "rule_based_recommendation",
    "rule_based_score",
    "rule_based_tier",
    "rule_based_reason",
    "positive_keyword_hits",
    "negative_keyword_hits",
    "evaluation_dimensions",
}


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


class LLMTransport(Protocol):
    def generate(self, *, system_prompt: str, user_prompt: str, response_schema: dict[str, Any]) -> LLMResponse:
        ...


class ShadowEvaluationError(RuntimeError):
    pass


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _supporting_text(job: dict[str, Any], key: str) -> str | None:
    for container_name in ("description", "requirements", "raw_extra"):
        container = job.get(container_name) or {}
        value = container.get(key)
        if isinstance(value, str) and value.strip():
            cleaned, _, _ = clean_vacancy_text(value)
            return cleaned or None
    return None


def _build_llm_input_and_context(
    canonical_job: dict[str, Any],
    candidate_profile: dict[str, Any],
    *,
    max_context_chars: int | None = DEFAULT_MAX_CONTEXT_CHARS,
) -> tuple[dict[str, Any], ContextQualityResult]:
    job_id = _job_id(canonical_job)
    if not job_id:
        raise ShadowEvaluationError("canonical job has no stable identifier")

    profile_version = str(candidate_profile.get("profile_version") or "").strip()
    if not profile_version:
        raise ShadowEvaluationError("candidate profile has no profile_version")

    position = canonical_job.get("position") or {}
    description = canonical_job.get("description") or {}
    location = canonical_job.get("location") or {}
    contract = canonical_job.get("contract") or {}

    raw_full_text = str(description.get("full_jd") or "")
    context = prepare_vacancy_context(raw_full_text, max_chars=max_context_chars)

    detail_status = str(description.get("detail_status") or "UNKNOWN").upper()
    if detail_status not in {"FULL", "PARTIAL", "UNAVAILABLE", "UNKNOWN"}:
        detail_status = "UNKNOWN"

    responsibilities = _supporting_text(canonical_job, "responsibilities_text") or context.responsibilities_text
    essential = _supporting_text(canonical_job, "essential_criteria_text") or context.essential_criteria_text
    desirable = _supporting_text(canonical_job, "desirable_criteria_text") or context.desirable_criteria_text

    fingerprint_material = json.dumps(
        {
            "job_id": job_id,
            "profile_version": profile_version,
            "full_text": context.full_text,
            "responsibilities_text": responsibilities,
            "essential_criteria_text": essential,
            "desirable_criteria_text": desirable,
        },
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    evaluation_id = hashlib.sha256(fingerprint_material).hexdigest()[:24]

    payload = {
        "schema_version": "LLM_EVALUATOR_INPUT_V0.1",
        "evaluation_id": evaluation_id,
        "candidate_profile_version": profile_version,
        "job": {
            "job_id": job_id,
            "title": _clean(position.get("title_raw")),
            "institution": _clean(position.get("institution_raw")),
            "location": _location_text(canonical_job),
            "country": location.get("country_name") or location.get("country_code"),
            "contract_type": contract.get("term_type") or position.get("employment_type"),
            "seniority": position.get("role_level"),
            "detail_status": detail_status,
            "full_text": context.full_text,
            "responsibilities_text": responsibilities,
            "essential_criteria_text": essential,
            "desirable_criteria_text": desirable,
            "source_url": _source_url(canonical_job),
        },
    }

    validator = Draft202012Validator(_load_schema(INPUT_SCHEMA_PATH))
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        raise ShadowEvaluationError("invalid LLM input: " + "; ".join(e.message for e in errors))

    serialized = json.dumps(payload, ensure_ascii=False)
    for key in PROHIBITED_INPUT_KEYS:
        if f'"{key}"' in serialized:
            raise ShadowEvaluationError(f"prohibited rule-based field leaked into LLM input: {key}")
    return payload, context


def build_llm_input(
    canonical_job: dict[str, Any],
    candidate_profile: dict[str, Any],
    *,
    max_context_chars: int | None = DEFAULT_MAX_CONTEXT_CHARS,
) -> dict[str, Any]:
    payload, _ = _build_llm_input_and_context(
        canonical_job,
        candidate_profile,
        max_context_chars=max_context_chars,
    )
    return payload


def _evidence_policy(job: dict[str, Any]) -> tuple[str, int]:
    detail_status = job["detail_status"]
    full_text = (job.get("full_text") or "").strip()
    auxiliary = any((job.get(k) or "").strip() for k in (
        "responsibilities_text",
        "essential_criteria_text",
        "desirable_criteria_text",
    ))
    if detail_status == "FULL" and full_text:
        return "FULL_JD", 100
    if detail_status == "PARTIAL" and full_text:
        return "PARTIAL_JD", 80
    if full_text or auxiliary:
        return "LIMITED", 55
    return "INSUFFICIENT", 30


def _system_prompt() -> str:
    return (
        "You are an independent academic-job semantic evaluator operating in shadow mode. "
        "Recall is more important than precision: a plausible relevant role should not be skipped merely because its title or wording is unusual. "
        "Reason from the actual vacancy text first and the candidate profile second. Distinguish mandatory requirements from preferred ones. "
        "Do not invent credentials, work authorization, licensure, methods, language skills, or seniority. "
        "A preferred criterion is not a hard blocker. If eligibility or fit is materially ambiguous, prefer REVIEW over unsupported SKIP. "
        "Use hard_blocker=true only when the vacancy explicitly states a mandatory requirement that the candidate evidence clearly cannot satisfy. "
        "Return only one JSON object conforming exactly to the supplied schema."
    )


def _user_prompt(llm_input: dict[str, Any], candidate_profile: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Evaluate scientific, methodological, seniority, transferable and eligibility fit independently.",
            "vacancy": llm_input["job"],
            "candidate_profile": candidate_profile,
            "decision_guidance": {
                "STRONG_APPLY": "clear and compelling realistic fit",
                "APPLY": "good realistic fit with manageable gaps",
                "REVIEW": "plausible or adjacent fit, or important ambiguity requiring human review",
                "SKIP": "clearly weak or unrealistic fit based on vacancy evidence",
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


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ShadowEvaluationError(f"malformed LLM JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ShadowEvaluationError("LLM response must be a JSON object")
    return parsed


def _validate_output(result: dict[str, Any], evaluation_id: str) -> dict[str, Any]:
    result = dict(result)
    result.setdefault("schema_version", "LLM_EVALUATION_V0.1")
    result.setdefault("evaluation_id", evaluation_id)
    if result.get("evaluation_id") != evaluation_id:
        raise ShadowEvaluationError("LLM response evaluation_id does not match request")
    validator = Draft202012Validator(_load_schema(OUTPUT_SCHEMA_PATH))
    errors = sorted(validator.iter_errors(result), key=lambda e: list(e.path))
    if errors:
        raise ShadowEvaluationError("invalid LLM output: " + "; ".join(e.message for e in errors))
    if result.get("hard_blocker") is True:
        reason = str(result.get("hard_blocker_reason") or "").strip()
        if not reason:
            raise ShadowEvaluationError("hard_blocker=true requires hard_blocker_reason")
    return result


def _append_jsonl(path: Path | None, row: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


class ShadowEvaluator:
    def __init__(
        self,
        *,
        transport: LLMTransport,
        candidate_profile: dict[str, Any],
        shadow_path: Path | None = None,
        telemetry_path: Path | None = None,
        cache_path: Path | None = None,
        max_context_chars: int | None = DEFAULT_MAX_CONTEXT_CHARS,
    ) -> None:
        self.transport = transport
        self.candidate_profile = candidate_profile
        self.shadow_path = shadow_path
        self.telemetry_path = telemetry_path
        self.cache_path = cache_path
        self.max_context_chars = max_context_chars
        self._cache = load_successful_cache(cache_path)

    def _telemetry(self, event: str, **fields: Any) -> None:
        _append_jsonl(
            self.telemetry_path,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **fields,
            },
        )

    def evaluate(self, canonical_job: dict[str, Any]) -> dict[str, Any]:
        llm_input, context = _build_llm_input_and_context(
            canonical_job,
            self.candidate_profile,
            max_context_chars=self.max_context_chars,
        )
        evaluation_id = llm_input["evaluation_id"]
        evidence_quality, confidence_cap = _evidence_policy(llm_input["job"])
        system_prompt = _system_prompt()
        user_prompt = _user_prompt(llm_input, self.candidate_profile)
        output_schema = _load_schema(OUTPUT_SCHEMA_PATH)
        transport_identity = _transport_identity(self.transport)
        cache_fingerprint = build_cache_fingerprint(
            llm_input=llm_input,
            candidate_profile=self.candidate_profile,
            system_prompt=system_prompt,
            output_schema=output_schema,
            transport_identity=transport_identity,
        )

        cached = self._cache.get(cache_fingerprint)
        if cached is not None:
            reused = copy.deepcopy(cached)
            reused["cache_hit"] = True
            reused["cache_reused_at"] = datetime.now(timezone.utc).isoformat()
            _append_jsonl(self.shadow_path, reused)
            self._telemetry(
                "llm_evaluation_cache_hit",
                evaluation_id=evaluation_id,
                job_id=llm_input["job"]["job_id"],
                cache_fingerprint=cache_fingerprint,
                model=cached.get("model"),
            )
            return reused

        self._telemetry(
            "llm_evaluation_start",
            evaluation_id=evaluation_id,
            job_id=llm_input["job"]["job_id"],
            cache_fingerprint=cache_fingerprint,
            detail_status=llm_input["job"]["detail_status"],
            context_original_chars=context.original_chars,
            context_cleaned_chars=context.cleaned_chars,
            context_final_chars=context.final_chars,
            context_truncated=context.truncated,
            context_truncation_strategy=context.truncation_strategy,
            context_boilerplate_lines_removed=context.boilerplate_lines_removed,
            context_duplicate_blocks_removed=context.duplicate_blocks_removed,
        )

        try:
            response = self.transport.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=output_schema,
            )
        except Exception as exc:
            self._telemetry(
                "llm_api_failure",
                evaluation_id=evaluation_id,
                cache_fingerprint=cache_fingerprint,
                error_type=type(exc).__name__,
                error=str(exc)[:500],
            )
            raise ShadowEvaluationError(f"LLM transport failed: {type(exc).__name__}: {exc}") from exc

        try:
            result = _validate_output(_extract_json(response.text), evaluation_id)
        except ShadowEvaluationError as exc:
            self._telemetry(
                "llm_response_invalid",
                evaluation_id=evaluation_id,
                cache_fingerprint=cache_fingerprint,
                error=str(exc)[:500],
                model=response.model,
            )
            raise

        result["evidence_quality"] = evidence_quality
        result["confidence"] = min(int(result["confidence"]), confidence_cap)
        result = _validate_output(result, evaluation_id)

        shadow_record = {
            "shadow_schema_version": "LLM_SHADOW_RESULT_V0.1",
            "evaluation_id": evaluation_id,
            "job_id": llm_input["job"]["job_id"],
            "candidate_profile_version": llm_input["candidate_profile_version"],
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "cache_fingerprint": cache_fingerprint,
            "cache_hit": False,
            "context_quality": {
                "original_chars": context.original_chars,
                "cleaned_chars": context.cleaned_chars,
                "final_chars": context.final_chars,
                "boilerplate_lines_removed": context.boilerplate_lines_removed,
                "duplicate_blocks_removed": context.duplicate_blocks_removed,
                "truncated": context.truncated,
                "truncation_strategy": context.truncation_strategy,
            },
            "llm_result": result,
        }
        _append_jsonl(self.shadow_path, shadow_record)
        append_cache_record(self.cache_path, shadow_record)
        self._cache[cache_fingerprint] = shadow_record
        self._telemetry(
            "llm_evaluation_stored",
            evaluation_id=evaluation_id,
            cache_fingerprint=cache_fingerprint,
            decision=result["decision"],
            confidence=result["confidence"],
            evidence_quality=result["evidence_quality"],
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
        )
        return shadow_record
