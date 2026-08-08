"""Privacy-safe HTTP outcome mapping shared by LINE provider adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json

_ERROR_MESSAGE_MAXIMUM_LENGTH = 500


@dataclass(frozen=True, slots=True)
class LineHttpFailure:
    category: str
    code: str
    message: str
    retry_after_seconds: int | None


def response_failure(response: object) -> LineHttpFailure:
    status_code = int(getattr(response, "status_code"))
    category = _failure_category(status_code)
    return LineHttpFailure(
        category,
        f"line_http_{status_code}",
        _response_message(response),
        _retry_after(response) if status_code == 429 else None,
    )


def response_request_id(response: object) -> str | None:
    return _header_text(response, "x-line-request-id", "X-Line-Request-Id")


def response_accepted_request_id(response: object) -> str | None:
    return _header_text(
        response,
        "x-line-accepted-request-id",
        "X-Line-Accepted-Request-Id",
    )


def _header_text(response: object, *names: str) -> str | None:
    headers = getattr(response, "headers", {})
    if not isinstance(headers, Mapping):
        return None
    value = next((headers.get(name) for name in names if headers.get(name)), None)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _failure_category(status_code: int) -> str:
    if status_code == 429:
        return "rate_limited"
    if 400 <= status_code < 500:
        return "rejected"
    return "unavailable"


def _response_message(response: object) -> str:
    payload = _response_payload(response)
    message = payload.get("message") if payload else None
    if not isinstance(message, str) or not message.strip():
        message = f"LINE provider returned HTTP {getattr(response, 'status_code')}"
    return message.strip()[:_ERROR_MESSAGE_MAXIMUM_LENGTH]


def _response_payload(response: object) -> dict[str, object]:
    try:
        payload = response.json()
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _retry_after(response: object) -> int | None:
    headers = getattr(response, "headers", {})
    if not isinstance(headers, Mapping):
        return None
    value = headers.get("Retry-After") or headers.get("retry-after")
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, seconds)


__all__ = [
    "LineHttpFailure",
    "response_accepted_request_id",
    "response_failure",
    "response_request_id",
]
