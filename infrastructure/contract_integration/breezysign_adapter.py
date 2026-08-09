"""Fail-closed BreezySign signature verification and configurable event normalization."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime

from domains.contract_integration.contract_event import (
    VerifiedContractEvent,
    canonical_payload_hash,
    map_provider_status,
)


class BreezySignHmacSha256Verifier:
    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def verify(self, raw_body: bytes, signature: str | None) -> bool:
        if not self._secret or not signature:
            return False
        supplied = signature.removeprefix("sha256=").strip().lower()
        expected = hmac.new(self._secret, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(supplied, expected)


class ConfiguredBreezySignEventNormalizer:
    """Exact field/status mappings are configuration, never guessed defaults."""

    def __init__(self, status_mapping: dict[str, str]) -> None:
        if not status_mapping:
            raise RuntimeError("BREEZYSIGN_STATUS_MAP_JSON must define exact provider statuses")
        self._status_mapping = status_mapping

    def normalize(self, raw_body: bytes) -> VerifiedContractEvent:
        payload = _object_payload(raw_body)
        return VerifiedContractEvent(
            provider="breezysign",
            provider_contract_id=_required_text(payload, "contract_id"),
            provider_event_id=_required_text(payload, "event_id"),
            event_type=_required_text(payload, "event"),
            contract_status=map_provider_status(payload.get("status"), self._status_mapping),
            occurred_at=_required_datetime(payload, "occurred_at"),
            canonical_payload_hash=canonical_payload_hash(payload),
        )


def _object_payload(raw_body: bytes) -> dict:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("external_payload_invalid") from error
    if not isinstance(payload, dict):
        raise ValueError("external_payload_invalid")
    return payload


def _required_text(payload: dict, name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("external_payload_invalid")
    return value.strip()


def _required_datetime(payload: dict, name: str) -> datetime:
    try:
        value = datetime.fromisoformat(_required_text(payload, name).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("external_payload_invalid") from error
    if value.tzinfo is None:
        raise ValueError("external_payload_invalid")
    return value


__all__ = [
    "BreezySignHmacSha256Verifier",
    "ConfiguredBreezySignEventNormalizer",
]

