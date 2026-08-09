"""Constant-time LINE webhook signature verification over the raw request body."""

from __future__ import annotations

import base64
import hashlib
import hmac


class LineWebhookSignatureVerifier:
    def __init__(self, channel_secret: str) -> None:
        normalized = channel_secret.strip()
        if not normalized:
            raise ValueError("LINE channel secret is required")
        self._channel_secret = normalized.encode("utf-8")

    def verify(self, raw_body: bytes, signature: str | None) -> bool:
        if not isinstance(raw_body, bytes) or not raw_body or not signature:
            return False
        digest = hmac.new(self._channel_secret, raw_body, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode("ascii")
        return hmac.compare_digest(expected, signature.strip())


__all__ = ["LineWebhookSignatureVerifier"]
