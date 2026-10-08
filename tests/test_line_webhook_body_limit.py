"""Unauthenticated LINE webhook byte limits are enforced before intake work."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import line_webhook_boundary as boundary


WEBHOOK_ALIASES = ("/webhook/line", "/webhook/line/", "/webhook", "/webhook/")


@pytest.fixture
def webhook_app(monkeypatch):
    seen = []

    def fingerprint(body):
        seen.append(("fingerprint", len(body)))
        return "request-fingerprint"

    def accept(body, signature, correlation_id):
        seen.append(("accept", len(body)))
        return SimpleNamespace(created_count=0, duplicate_count=0)

    async def receipt(*args):
        seen.append(("receipt", None))

    monkeypatch.setattr(boundary, "webhook_request_fingerprint", fingerprint)
    monkeypatch.setattr(boundary, "get_line_webhook_intake", lambda: SimpleNamespace(accept=accept))
    monkeypatch.setattr(boundary, "_record_receipt", receipt)

    app = FastAPI()
    for path in WEBHOOK_ALIASES:
        app.add_api_route(path, boundary.canonical_line_webhook, methods=["POST"])
    return TestClient(app), seen


@pytest.mark.parametrize("path", WEBHOOK_ALIASES)
def test_exact_limit_reaches_intake(path, webhook_app):
    client, seen = webhook_app
    size = boundary.MAX_LINE_WEBHOOK_BODY_BYTES

    response = client.post(path, content=b"x" * size)

    assert response.status_code == 200
    assert seen == [("fingerprint", size), ("accept", size), ("receipt", None)]


@pytest.mark.parametrize("path", WEBHOOK_ALIASES)
def test_over_limit_content_length_skips_fingerprint_and_intake(path, webhook_app):
    client, seen = webhook_app
    size = boundary.MAX_LINE_WEBHOOK_BODY_BYTES + 1

    response = client.post(path, content=b"x" * size)

    assert response.status_code == 413
    assert seen == []


@pytest.mark.parametrize("path", WEBHOOK_ALIASES)
def test_over_limit_chunked_stream_skips_fingerprint_and_intake(path, webhook_app):
    client, seen = webhook_app
    size = boundary.MAX_LINE_WEBHOOK_BODY_BYTES

    response = client.post(path, content=iter((b"x" * size, b"x")))

    assert response.status_code == 413
    assert seen == []


def test_declared_over_limit_rejected_without_reading_stream():
    class UnreadRequest:
        headers = {"content-length": str(boundary.MAX_LINE_WEBHOOK_BODY_BYTES + 1)}

        async def stream(self):
            raise AssertionError("stream should not be opened")
            yield b""  # pragma: no cover

    with pytest.raises(HTTPException) as exc:
        asyncio.run(boundary._read_webhook_body(UnreadRequest()))

    assert exc.value.status_code == 413
