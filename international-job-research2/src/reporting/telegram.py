from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import requests


class TelegramTransientError(RuntimeError):
    pass


class TelegramPermanentError(RuntimeError):
    pass


def _token() -> str:
    return str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _chat_ids() -> list[str]:
    raw = str(os.environ.get("TELEGRAM_CHAT_IDS") or "")
    return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]


def format_summary(summary: dict[str, Any]) -> str:
    rec = summary.get("recommendations") or {}
    events = summary.get("events") or {}
    health = summary.get("source_health") or {}
    today = int(summary.get("today_actionable", 0) or 0)
    tail = "No new or materially changed actionable vacancies." if today == 0 else f"Actionable changes today: {today}"
    return "\n".join([
        "✅ Academic job search completed",
        f"Run: {summary.get('run_id', '')}",
        f"Current actionable: {summary.get('current_actionable', 0)}",
        f"STRONG: {rec.get('STRONG_APPLY', 0)} | APPLY: {rec.get('APPLY', 0)} | REVIEW: {rec.get('REVIEW', 0)}",
        f"New: {events.get('NEW', 0)} | Changed: {events.get('MATERIALLY_CHANGED', 0)} | Reopened: {events.get('REOPENED', 0)}",
        f"Review queue: {summary.get('review_queue', 0)} | Low: {summary.get('low_priority', 0)}",
        f"Sources: ✅ {health.get('OK', 0)} | ⚠️ {health.get('PARTIAL', 0)} | ❌ {health.get('ERROR', 0)} | ? {health.get('UNKNOWN', 0)}",
        tail,
    ])


def _sleep_seconds(attempt: int, response: requests.Response | None = None) -> float:
    if response is not None:
        try:
            retry_after = ((response.json().get("parameters") or {}).get("retry_after"))
            if retry_after is not None:
                return min(30.0, max(1.0, float(retry_after)))
        except (ValueError, TypeError, AttributeError):
            pass
    return min(8.0, float(2 ** (attempt - 1)))


def _post(method: str, *, max_attempts: int = 4, **kwargs):
    token = _token()
    if not token:
        raise TelegramPermanentError("TELEGRAM_BOT_TOKEN is missing")
    url = f"https://api.telegram.org/bot{token}/{method}"
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(url, timeout=(15, 60), **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt >= max_attempts:
                raise TelegramTransientError(f"Telegram network unavailable during {method}") from exc
            time.sleep(_sleep_seconds(attempt))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt >= max_attempts:
                raise TelegramTransientError(f"Telegram temporary HTTP {response.status_code} during {method}")
            time.sleep(_sleep_seconds(attempt, response))
            continue
        if response.status_code >= 400:
            raise TelegramPermanentError(f"Telegram API HTTP {response.status_code} during {method}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramTransientError("Telegram returned invalid JSON") from exc
        if not payload.get("ok"):
            code = int(payload.get("error_code") or 0)
            description = str(payload.get("description") or "Telegram API rejected request")
            if code == 429 or code >= 500:
                raise TelegramTransientError(description)
            raise TelegramPermanentError(description)
        return payload
    raise TelegramTransientError(f"Telegram request failed during {method}")


def check_configuration() -> dict[str, Any]:
    chats = _chat_ids()
    if not chats:
        raise TelegramPermanentError("TELEGRAM_CHAT_IDS is missing")
    bot = _post("getMe")
    for chat_id in chats:
        _post("getChat", data={"chat_id": chat_id})
    return {"ok": True, "bot_username": (bot.get("result") or {}).get("username", ""), "chat_count": len(chats)}


def send_report(summary: dict[str, Any], report_path: Path | None = None) -> None:
    chats = _chat_ids()
    if not chats:
        raise TelegramPermanentError("TELEGRAM_CHAT_IDS is missing")
    text = format_summary(summary)
    send_always = str(os.environ.get("TELEGRAM_SEND_REPORT_ALWAYS") or "").strip().lower() in {"1", "true", "yes"}
    send_document = send_always or int(summary.get("today_actionable", 0) or 0) > 0
    for chat_id in chats:
        _post("sendMessage", data={"chat_id": chat_id, "text": text})
        if send_document and report_path and report_path.exists():
            with report_path.open("rb") as handle:
                _post(
                    "sendDocument",
                    data={"chat_id": chat_id, "caption": "International academic job report"},
                    files={"document": (report_path.name, handle, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                )
