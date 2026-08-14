"""HTTP adapter implementing typed LINE push-message provider outcomes."""

from __future__ import annotations

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import requests

from domains.line.delivery import LineDeliveryRequest
from domains.line.identities import LineProviderMessageId
from infrastructure.line.http_outcomes import (
    response_accepted_request_id,
    response_failure,
    response_request_id,
)
from subsystems.line.delivery_contracts import (
    LineProviderOutcome,
    LineProviderOutcomeType,
)

_PUSH_ENDPOINT = "https://api.line.me/v2/bot/message/push"


class LineMessagingApiAdapter:
    def __init__(
        self,
        channel_access_token: str,
        *,
        session: Any | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        normalized = channel_access_token.strip()
        if not normalized:
            raise ValueError("LINE channel access token is required")
        self._access_token = normalized
        self._session = session or requests.Session()
        self._timeout_seconds = timeout_seconds

    def send(self, request: LineDeliveryRequest) -> LineProviderOutcome:
        try:
            response = self._session.post(
                _PUSH_ENDPOINT,
                headers=self._headers(request),
                data=_request_body(request),
                timeout=self._timeout_seconds,
            )
        except requests.Timeout:
            return _failed(LineProviderOutcomeType.TIMEOUT, "line_provider_timeout")
        except requests.RequestException:
            return _failed(
                LineProviderOutcomeType.UNAVAILABLE,
                "line_provider_unavailable",
            )
        if 200 <= int(response.status_code) < 300:
            request_id = _provider_message_identity(response, request)
            return LineProviderOutcome(
                LineProviderOutcomeType.SUCCESS,
                provider_message_id=LineProviderMessageId(request_id),
            )
        accepted_request_id = response_accepted_request_id(response)
        if int(response.status_code) == 409 and accepted_request_id:
            return LineProviderOutcome(
                LineProviderOutcomeType.SUCCESS,
                provider_message_id=LineProviderMessageId(
                    _sent_message_id(response) or accepted_request_id
                ),
            )
        return _failure_outcome(response)

    def _headers(self, request: LineDeliveryRequest) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "X-Line-Retry-Key": str(
                uuid5(NAMESPACE_URL, f"line-delivery:{request.idempotency_key.value}")
            ),
        }


def _request_body(request: LineDeliveryRequest) -> str:
    message = json.loads(request.payload_json)
    payload = {"messages": [message], "to": request.recipient.identity.value}
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _failure_outcome(response: object) -> LineProviderOutcome:
    failure = response_failure(response)
    return LineProviderOutcome(
        LineProviderOutcomeType(failure.category),
        error_code=failure.code,
        error_message=failure.message,
        retry_after_seconds=failure.retry_after_seconds,
    )


def _provider_message_identity(response, request):
    return (
        _sent_message_id(response)
        or response_request_id(response)
        or request.idempotency_key.value
    )


def _sent_message_id(response: object) -> str | None:
    try:
        sent_messages = response.json().get("sentMessages", [])
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(sent_messages, list) or not sent_messages:
        return None
    first = sent_messages[0]
    if not isinstance(first, dict):
        return None
    message_id = first.get("id")
    if not isinstance(message_id, str) or not message_id.strip():
        return None
    return message_id.strip()


def _failed(outcome_type, error_code):
    return LineProviderOutcome(
        outcome_type,
        error_code=error_code,
        error_message=error_code.replace("_", " "),
    )


__all__ = ["LineMessagingApiAdapter"]
