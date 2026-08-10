"""LINE Login ID-token verification adapter for public LIFF identity requests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import requests

from domains.line.identities import LineUserId
from subsystems.line.identity_contracts import VerifiedLiffIdentity

VERIFY_ID_TOKEN_URL = "https://api.line.me/oauth2/v2.1/verify"


class InvalidLiffTokenError(ValueError):
    """Raised when LINE rejects an ID token or its claims are invalid."""


class LiffVerificationUnavailableError(RuntimeError):
    """Raised when the LINE Login verification service cannot be reached."""


class LineLoginTokenVerifier:
    def __init__(
        self,
        channel_id: str,
        *,
        post: Callable[..., object] = requests.post,
        timeout_seconds: float = 8.0,
    ) -> None:
        normalized_channel_id = channel_id.strip()
        if not normalized_channel_id:
            raise ValueError("LINE Login channel ID is required")
        self._channel_id = normalized_channel_id
        self._post = post
        self._timeout_seconds = timeout_seconds

    def verify(self, id_token: str) -> VerifiedLiffIdentity:
        token = id_token.strip()
        if not token:
            raise InvalidLiffTokenError("LIFF ID Token is required")
        payload = self._request_verification(token)
        return self._verified_identity(payload)

    def _request_verification(self, token: str) -> dict[str, object]:
        try:
            response = self._post(
                VERIFY_ID_TOKEN_URL,
                data={"id_token": token, "client_id": self._channel_id},
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as error:
            raise LiffVerificationUnavailableError(
                "LINE Login verification is unavailable"
            ) from error
        if not getattr(response, "ok", False):
            raise InvalidLiffTokenError("LIFF ID Token is invalid or expired")
        try:
            payload = response.json()
        except (TypeError, ValueError) as error:
            raise InvalidLiffTokenError("LIFF verification response is invalid") from error
        if not isinstance(payload, dict):
            raise InvalidLiffTokenError("LIFF verification response is invalid")
        return payload

    def _verified_identity(self, payload: dict[str, object]) -> VerifiedLiffIdentity:
        subject = str(payload.get("sub") or "").strip()
        audience = str(payload.get("aud") or "").strip()
        if not subject or audience != self._channel_id:
            raise InvalidLiffTokenError("LIFF token identity or audience is invalid")
        try:
            expires_at = datetime.fromtimestamp(int(payload["exp"]), timezone.utc)
        except (KeyError, TypeError, ValueError, OSError) as error:
            raise InvalidLiffTokenError("LIFF token expiry is invalid") from error
        if expires_at <= datetime.now(timezone.utc):
            raise InvalidLiffTokenError("LIFF ID Token has expired")
        return VerifiedLiffIdentity(LineUserId(subject), audience, expires_at)


__all__ = [
    "InvalidLiffTokenError",
    "LiffVerificationUnavailableError",
    "LineLoginTokenVerifier",
]
