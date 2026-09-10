from __future__ import annotations

import json
from typing import Any

FAILURE_CLASSES = {
    "AUTH_PERMISSION",
    "RATE_LIMIT",
    "UPSTREAM_5XX",
    "TIMEOUT",
    "NETWORK_TRANSPORT",
    "BLOCKED_ANTI_BOT",
    "PARSER_SCHEMA",
    "CONFIGURATION",
    "INVALID_ARTIFACT",
    "MISSING_ARTIFACT",
    "UNKNOWN",
}


def _response_status(exc: Exception) -> int | None:
    response: Any = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if status is not None:
            try:
                return int(status)
            except (TypeError, ValueError):
                pass
        if isinstance(response, dict):
            meta = response.get("ResponseMetadata") or {}
            status = meta.get("HTTPStatusCode")
            if status is not None:
                try:
                    return int(status)
                except (TypeError, ValueError):
                    pass
    code = getattr(exc, "code", None)
    if code is not None:
        try:
            return int(code)
        except (TypeError, ValueError):
            pass
    return None


def _error_code(exc: Exception) -> str:
    response: Any = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error") or {}
        return str(error.get("Code") or "").strip()
    return ""


def classify_failure(exc: Exception) -> str:
    """Classify runtime failures without changing retry or collector behavior."""
    type_name = type(exc).__name__.lower()
    message = str(exc).lower()
    error_code = _error_code(exc).lower()
    status = _response_status(exc)

    if (
        error_code in {"accessdenied", "unauthorized", "invalidaccesskeyid", "signaturedoesnotmatch"}
        or "access denied" in message
        or "unauthorized" in message
        or "invalid access key" in message
        or "invalidaccesskeyid" in message
        or "signaturedoesnotmatch" in message
    ):
        return "AUTH_PERMISSION"

    if status == 429 or "too many requests" in message or "rate limit" in message or "ratelimit" in message:
        return "RATE_LIMIT"

    if status is not None and 500 <= status <= 599:
        return "UPSTREAM_5XX"

    if (
        "timeout" in type_name
        or "timed out" in message
        or "timeout" in message
    ):
        return "TIMEOUT"

    if any(
        marker in message
        for marker in (
            "captcha",
            "anti-bot",
            "antibot",
            "bot challenge",
            "challenge page",
            "cloudflare challenge",
            "blocked by",
        )
    ):
        return "BLOCKED_ANTI_BOT"

    if any(
        marker in type_name
        for marker in ("connectionerror", "proxyerror", "sslerror", "newconnectionerror")
    ) or any(
        marker in message
        for marker in (
            "connection reset",
            "connection refused",
            "name or service not known",
            "temporary failure in name resolution",
            "dns",
            "network is unreachable",
        )
    ):
        return "NETWORK_TRANSPORT"

    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)):
        return "PARSER_SCHEMA"

    if (
        isinstance(exc, KeyError)
        or "missing required environment variable" in message
        or "unknown production shard" in message
        or "must be all or a positive integer" in message
    ):
        return "CONFIGURATION"

    return "UNKNOWN"
