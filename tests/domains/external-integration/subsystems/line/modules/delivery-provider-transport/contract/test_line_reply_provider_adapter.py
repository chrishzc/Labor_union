"""Contract oracle for the LINE Reply provider adapter."""

from __future__ import annotations

import json

from infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from subsystems.line.delivery_contracts import LineProviderOutcomeType


class FakeResponse:
    status_code = 200
    headers = {"x-line-request-id": "reply-request-1"}

    def json(self):
        return {}


class ReplySession:
    def __init__(self) -> None:
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def test_reply_adapter_uses_reply_endpoint_and_marks_provider_identity() -> None:
    session = ReplySession()

    outcome = LineMessagingApiAdapter("token", session=session).reply(
        "reply-token-1",
        {"type": "text", "text": "免費回覆"},
    )

    assert outcome.outcome_type is LineProviderOutcomeType.SUCCESS
    assert outcome.provider_message_id.value == "reply:reply-request-1"
    assert session.calls[0][0].endswith("/v2/bot/message/reply")
    assert json.loads(session.calls[0][1]["data"]) == {
        "replyToken": "reply-token-1",
        "messages": [{"type": "text", "text": "免費回覆"}],
    }
