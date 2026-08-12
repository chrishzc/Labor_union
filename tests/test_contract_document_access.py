from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from subsystems.contract_signing.document_access import (
    create_document_access_credential,
    token_matches_credential,
)


def test_document_access_token_is_opaque_and_stores_only_a_digest():
    credential = create_document_access_credential(
        now=datetime(2026, 8, 10, tzinfo=timezone.utc),
        ttl=timedelta(hours=24),
    )

    assert credential.raw_token != credential.token_sha256
    assert len(credential.token_sha256) == 64
    assert token_matches_credential(credential.raw_token, credential.token_sha256)
    assert not token_matches_credential("wrong-token", credential.token_sha256)


@pytest.mark.parametrize("ttl", [timedelta(minutes=4), timedelta(days=8)])
def test_document_access_token_requires_a_bounded_expiry(ttl):
    with pytest.raises(ValueError, match="TTL"):
        create_document_access_credential(
            now=datetime(2026, 8, 10, tzinfo=timezone.utc),
            ttl=ttl,
        )
