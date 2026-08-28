"""
File: final_document_preview_token.py
Description: 將最終契約 Preview facts 封裝成不洩漏 fingerprint 的短效 opaque token。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any


_TOKEN = re.compile(r"^cp_[A-Za-z0-9_-]{43}$")


class FinalDocumentPreviewTokenError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class HmacFinalDocumentPreviewTokenCodec:
    """Issue deterministic opaque tokens; verification always uses fresh server facts."""

    def __init__(self, secret: str | bytes) -> None:
        raw = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not isinstance(raw, bytes) or len(raw) < 32:
            raise ValueError("contract preview token secret must contain at least 32 bytes")
        self._secret = raw

    def issue(self, payload: Mapping[str, Any]) -> str:
        digest = hmac.new(self._secret, _canonical(payload), hashlib.sha256).digest()
        encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return f"cp_{encoded}"

    def verify(self, token: str, payload: Mapping[str, Any]) -> None:
        if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
            raise FinalDocumentPreviewTokenError("final_document_preview_token_invalid")
        expected = self.issue(payload)
        if not hmac.compare_digest(token, expected):
            raise FinalDocumentPreviewTokenError("final_document_preview_stale")


def _canonical(payload: Mapping[str, Any]) -> bytes:
    if not isinstance(payload, Mapping):
        raise TypeError("final document preview payload must be a mapping")
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


__all__ = [
    "FinalDocumentPreviewTokenError",
    "HmacFinalDocumentPreviewTokenCodec",
]
