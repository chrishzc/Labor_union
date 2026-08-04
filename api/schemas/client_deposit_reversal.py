"""Typed HTTP contracts for a deposit receipt reversal."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DepositReversalPreviewBody(_StrictModel):
    original_ledger_entry_id: int = Field(gt=0)
    reversal_occurred_on: date


class DepositReversalApplyBody(DepositReversalPreviewBody):
    expected_account_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class DepositReversalPreviewView(_StrictModel):
    account_version: int = Field(ge=0)
    candidate: dict[str, Any]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class DepositReversalReceiptView(_StrictModel):
    case_no: str
    account_version: int = Field(ge=0)
    original_ledger_entry_id: int = Field(gt=0)
    reversal_amount_ntd: int = Field(gt=0)
    lifecycle_intent: str
    anomaly_code: str | None
