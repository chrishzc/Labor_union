"""Per-request Contract Integration construction with fail-closed provider config."""

from __future__ import annotations

import json
import os

from infrastructure.contract_integration.breezysign_adapter import (
    BreezySignHmacSha256Verifier,
    ConfiguredBreezySignEventNormalizer,
)
from infrastructure.mysql.contract_integration_unit_of_work import (
    open_contract_integration_unit_of_work,
)
from subsystems.contract_integration.application import ContractWebhookApplication


def get_contract_webhook_application() -> ContractWebhookApplication:
    secret = os.getenv("BREEZYSIGN_WEBHOOK_SECRET", "").strip()
    status_mapping = _status_mapping()
    if not secret:
        raise RuntimeError("BREEZYSIGN_WEBHOOK_SECRET is not configured")
    return ContractWebhookApplication(
        open_contract_integration_unit_of_work,
        BreezySignHmacSha256Verifier(secret),
        ConfiguredBreezySignEventNormalizer(status_mapping),
    )


def breezysign_signature_header() -> str:
    header = os.getenv("BREEZYSIGN_SIGNATURE_HEADER", "").strip()
    if not header:
        raise RuntimeError("BREEZYSIGN_SIGNATURE_HEADER is not configured")
    return header


def _status_mapping() -> dict[str, str]:
    configured = os.getenv("BREEZYSIGN_STATUS_MAP_JSON", "").strip()
    try:
        value = json.loads(configured) if configured else {}
    except json.JSONDecodeError as error:
        raise RuntimeError("BREEZYSIGN_STATUS_MAP_JSON is invalid") from error
    if not isinstance(value, dict):
        raise RuntimeError("BREEZYSIGN_STATUS_MAP_JSON must be an object")
    return {str(key): str(mapped) for key, mapped in value.items()}


__all__ = ["breezysign_signature_header", "get_contract_webhook_application"]

