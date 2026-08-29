"""Stage 4 tests for verified LIFF identity evidence."""

from datetime import datetime, timedelta, timezone

import pytest
import requests

from infrastructure.line.liff_token_verifier import (
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
    LineLoginTokenVerifier,
)


class FakeResponse:
    def __init__(self, payload, *, ok=True) -> None:
        self._payload = payload
        self.ok = ok

    def json(self):
        return self._payload


def test_liff_verifier_returns_subject_only_after_audience_validation() -> None:
    expiry = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())
    verifier = LineLoginTokenVerifier(
        "login-channel-1",
        post=lambda *args, **kwargs: FakeResponse(
            {"sub": "U-trusted", "aud": "login-channel-1", "exp": expiry}
        ),
    )

    verified = verifier.verify("signed-id-token")

    assert verified.line_user_id.value == "U-trusted"
    assert verified.audience == "login-channel-1"


def test_liff_verifier_rejects_wrong_audience() -> None:
    expiry = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())
    verifier = LineLoginTokenVerifier(
        "expected-channel",
        post=lambda *args, **kwargs: FakeResponse(
            {"sub": "U-user", "aud": "other-channel", "exp": expiry}
        ),
    )

    with pytest.raises(InvalidLiffTokenError, match="audience"):
        verifier.verify("signed-id-token")


def test_liff_verifier_rejects_missing_audience_claim() -> None:
    expiry = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())
    verifier = LineLoginTokenVerifier(
        "expected-channel",
        post=lambda *args, **kwargs: FakeResponse({"sub": "U-user", "exp": expiry}),
    )

    with pytest.raises(InvalidLiffTokenError, match="audience"):
        verifier.verify("signed-id-token")


def test_liff_verifier_reports_provider_unavailability() -> None:
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("offline")

    verifier = LineLoginTokenVerifier("login-channel", post=unavailable)

    with pytest.raises(LiffVerificationUnavailableError):
        verifier.verify("signed-id-token")
