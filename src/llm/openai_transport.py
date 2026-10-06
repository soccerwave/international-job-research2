from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from .shadow_evaluator import LLMResponse


@dataclass(frozen=True)
class OpenAITransportConfig:
    api_key: str
    model: str = "gpt-6-luna"
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 120.0


class OpenAIChatCompletionsTransport:
    """OpenAI Structured Outputs adapter for the L2 LLMTransport protocol.

    Model choice is configuration, not evaluator policy. L2 defaults to the
    low-cost tier but callers may select a stronger model without changing
    semantic evaluation code.
    """

    def __init__(self, config: OpenAITransportConfig) -> None:
        if not config.api_key.strip():
            raise ValueError("OpenAI API key must not be empty")
        if not config.model.strip():
            raise ValueError("OpenAI model must not be empty")
        self.config = config

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
    ) -> LLMResponse:
        started = time.perf_counter()
        response = requests.post(
            self.config.base_url.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": "Bearer " + self.config.api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "llm_evaluation_v0_1",
                        "strict": True,
                        "schema": response_schema,
                    },
                },
            },
            timeout=self.config.timeout_seconds,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        payload = response.json()

        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI response contained no choices")
        message = choices[0].get("message") or {}
        refusal = message.get("refusal")
        if refusal:
            raise RuntimeError("OpenAI structured-output refusal: " + str(refusal))
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("OpenAI response contained no text content")

        usage = payload.get("usage") or {}
        return LLMResponse(
            text=text,
            model=payload.get("model") or self.config.model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
        )
