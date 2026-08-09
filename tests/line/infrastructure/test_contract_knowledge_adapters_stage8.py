"""Stage 8 provider adapter and rebuildable index contracts."""

import hashlib
import hmac
import json

import pytest

from domains.contract_integration.contract_event import ContractProjectionStatus
from infrastructure.contract_integration.breezysign_adapter import (
    BreezySignHmacSha256Verifier,
    ConfiguredBreezySignEventNormalizer,
)


def test_breezysign_hmac_verifier_accepts_only_matching_signature() -> None:
    body = b'{"event_id":"event-1"}'
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    verifier = BreezySignHmacSha256Verifier("secret")

    assert verifier.verify(body, f"sha256={signature}") is True
    assert verifier.verify(body, "sha256=bad") is False
    assert verifier.verify(body, None) is False


def test_breezysign_normalizer_requires_explicit_exact_fields() -> None:
    payload = {
        "event_id": "evt-1",
        "event": "contract.changed",
        "contract_id": "contract-1",
        "status": "provider-completed",
        "occurred_at": "2026-08-09T10:00:00Z",
    }
    normalizer = ConfiguredBreezySignEventNormalizer(
        {"provider-completed": "signed"}
    )

    event = normalizer.normalize(json.dumps(payload).encode("utf-8"))

    assert event.contract_status is ContractProjectionStatus.SIGNED
    assert event.provider_event_id == "evt-1"


def test_normalizer_without_provider_status_contract_is_disabled() -> None:
    with pytest.raises(RuntimeError, match="BREEZYSIGN_STATUS_MAP_JSON"):
        ConfiguredBreezySignEventNormalizer({})

