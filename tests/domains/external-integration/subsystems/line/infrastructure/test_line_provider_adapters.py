"""Contract tests for LINE signature, delivery, media, and Rich Menu adapters."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json

import requests

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import (
    LineRichMenuPublicationId,
    LineUserId,
)
from domains.line.media import LineMediaCategory, LineMediaMetadata
from domains.line.identities import LineSourceIdentity, LineSourceType
from infrastructure.line.media_adapters import FileSystemLineMediaObjectStore
from infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from infrastructure.line.rich_menu_api_adapter import LineRichMenuApiAdapter
from infrastructure.line.signature_verifier import LineWebhookSignatureVerifier
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.delivery_contracts import LineProviderOutcomeType
from subsystems.line.rich_menu_contracts import (
    LineRichMenuProviderOutcomeType,
    LineRichMenuProviderRequest,
)

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, content=b""):
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.headers = {} if headers is None else headers
        self.content = content

    def json(self):
        return self._payload


class PushSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


class RichMenuSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def _delivery_request() -> LineDeliveryRequest:
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId("U-customer")),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": "測試"}),
        NOW,
        IdempotencyKey("delivery:case-1:notice"),
        CorrelationId("correlation:case-1"),
        "order",
        "CASE-1",
    )


def test_signature_verifier_uses_raw_request_body() -> None:
    body = b'{"events":[]}'
    digest = hmac.new(b"secret", body, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode("ascii")
    verifier = LineWebhookSignatureVerifier("secret")

    assert verifier.verify(body, signature) is True
    assert verifier.verify(body + b" ", signature) is False


def test_push_adapter_sends_retry_key_and_maps_success() -> None:
    response = FakeResponse(
        200,
        {"sentMessages": [{"id": "provider-message-1"}]},
        {"x-line-request-id": "request-1"},
    )
    session = PushSession(response=response)
    outcome = LineMessagingApiAdapter("token", session=session).send(
        _delivery_request()
    )

    assert outcome.outcome_type is LineProviderOutcomeType.SUCCESS
    assert outcome.provider_message_id.value == "provider-message-1"
    headers = session.calls[0][1]["headers"]
    assert headers["X-Line-Retry-Key"]
    assert headers["Authorization"] == "Bearer token"


def test_push_adapter_treats_accepted_retry_as_success() -> None:
    response = FakeResponse(
        409,
        {"message": "The retry key is already accepted"},
        {"x-line-accepted-request-id": "accepted-request-1"},
    )
    outcome = LineMessagingApiAdapter(
        "token",
        session=PushSession(response=response),
    ).send(_delivery_request())

    assert outcome.outcome_type is LineProviderOutcomeType.SUCCESS
    assert outcome.provider_message_id.value == "accepted-request-1"


def test_push_adapter_maps_rate_limit_and_timeout() -> None:
    limited = LineMessagingApiAdapter(
        "token",
        session=PushSession(
            response=FakeResponse(429, {"message": "slow down"}, {"Retry-After": "7"})
        ),
    ).send(_delivery_request())
    timed_out = LineMessagingApiAdapter(
        "token",
        session=PushSession(error=requests.Timeout()),
    ).send(_delivery_request())

    assert limited.outcome_type is LineProviderOutcomeType.RATE_LIMITED
    assert limited.retry_after_seconds == 7
    assert timed_out.outcome_type is LineProviderOutcomeType.TIMEOUT


def test_filesystem_media_store_is_content_addressed(tmp_path) -> None:
    content = b"line-image"
    digest = hashlib.sha256(content).hexdigest()
    metadata = LineMediaMetadata(
        "provider-media-1",
        LineSourceIdentity(LineSourceType.USER, "U-user", LineUserId("U-user")),
        "image/png",
        len(content),
        digest,
        NOW,
        LineMediaCategory.USER_UPLOAD,
    )
    store = FileSystemLineMediaObjectStore(tmp_path)

    first = store.put(metadata, content)
    second = store.put(metadata, content)

    assert first == second
    assert (tmp_path / first).read_bytes() == content


def test_rich_menu_publish_creates_then_uploads() -> None:
    session = RichMenuSession(
        [FakeResponse(200, {"richMenuId": "richmenu-1"}), FakeResponse(200)]
    )
    adapter = LineRichMenuApiAdapter(
        "token",
        lambda _reference: (b"png", "image/png"),
        session=session,
    )
    request = LineRichMenuProviderRequest(
        LineRichMenuPublicationId(1),
        canonical_line_payload_json(
            {
                "name": "menu",
                "size": {"width": 2500, "height": 843},
                "selected": True,
                "chat_bar_text": "選單",
                "buttons": [
                    {
                        "bounds": {"x": 0, "y": 0, "width": 2500, "height": 843},
                        "action": {"type": "message", "text": "開始"},
                    }
                ],
            }
        ),
        "rich-menu/menu.png",
    )

    outcome = adapter.publish(request)

    assert outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS
    assert outcome.provider_menu_id == "richmenu-1"
    assert [call[0] for call in session.calls] == ["post", "post"]
    assert json.loads(session.calls[0][2]["data"])["chatBarText"] == "選單"
