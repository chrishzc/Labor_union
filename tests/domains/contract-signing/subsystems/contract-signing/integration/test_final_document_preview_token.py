"""
File: test_final_document_preview_token.py
Description: 驗證最終契約 Preview token 的 opaque、fresh-fact 與防竄改契約。
"""

import pytest

from subsystems.contract_signing.final_document_preview_token import (
    FinalDocumentPreviewTokenError,
    HmacFinalDocumentPreviewTokenCodec,
)


def test_token_is_opaque_and_deterministically_binds_fresh_facts() -> None:
    codec = HmacFinalDocumentPreviewTokenCodec("s" * 32)
    payload = {
        "session_id": "ces_" + "a" * 32,
        "status_version": 3,
        "staging_fingerprint": "f" * 64,
        "orders_fingerprint": "e" * 64,
    }

    token = codec.issue(payload)

    assert token.startswith("cp_")
    assert payload["staging_fingerprint"] not in token
    assert payload["orders_fingerprint"] not in token
    codec.verify(token, payload)


def test_token_rejects_changed_facts_and_malformed_input() -> None:
    codec = HmacFinalDocumentPreviewTokenCodec(b"k" * 32)
    payload = {"status_version": 3, "staging_fingerprint": "f" * 64}
    token = codec.issue(payload)

    with pytest.raises(FinalDocumentPreviewTokenError) as stale:
        codec.verify(token, {**payload, "status_version": 4})
    with pytest.raises(FinalDocumentPreviewTokenError) as invalid:
        codec.verify("not-a-token", payload)

    assert stale.value.code == "final_document_preview_stale"
    assert invalid.value.code == "final_document_preview_token_invalid"


@pytest.mark.parametrize("secret", ["", "short", b"x" * 31])
def test_codec_rejects_weak_secret(secret: str | bytes) -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        HmacFinalDocumentPreviewTokenCodec(secret)
