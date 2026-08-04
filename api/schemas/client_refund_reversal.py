"""Typed HTTP contracts for Client Refund and Client Reversal."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientRefundPreviewBody(_StrictModel):
    finance_import_row_ids: list[int] = Field(min_length=1)
    obligation_identities: list[str] = Field(min_length=1)


class ClientRefundApplyBody(ClientRefundPreviewBody):
    expected_account_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class ClientReversalPreviewBody(_StrictModel):
    ledger_entry_ids: list[int] = Field(min_length=1)
    occurred_on: date


class ClientReversalApplyBody(ClientReversalPreviewBody):
    expected_account_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class ClientRefundReturnPreviewBody(_StrictModel):
    finance_import_row_id: int = Field(gt=0)
    refund_ledger_entry_id: int = Field(gt=0)


class ClientRefundReturnApplyBody(ClientRefundReturnPreviewBody):
    expected_account_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class ClientRefundReversalPreviewView(_StrictModel):
    account_version: int = Field(ge=0)
    candidate: dict[str, Any]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClientRefundReversalReceiptView(_StrictModel):
    case_no: str
    correction_type: str
    account_version: int = Field(ge=0)
    correction_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_entry_count: int = Field(ge=0)
    allocation_count: int = Field(ge=0)
    affected_obligations: list[str]


class ClientRefundReversalQueryView(_StrictModel):
    case_no: str
    account_version: int = Field(ge=0)
    refund_obligations: list[dict[str, Any]]
    subsidy_return_obligations: list[dict[str, Any]]
    reversal_targets: list[dict[str, Any]]
    refund_return_targets: list[dict[str, Any]]


__all__ = [
    "ClientRefundApplyBody",
    "ClientRefundPreviewBody",
    "ClientRefundReversalPreviewView",
    "ClientRefundReversalQueryView",
    "ClientRefundReversalReceiptView",
    "ClientRefundReturnApplyBody",
    "ClientRefundReturnPreviewBody",
    "ClientReversalApplyBody",
    "ClientReversalPreviewBody",
]
