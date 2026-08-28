"""
File: historical_completion.py
Description: 定義 HOB-E Step 11 fresh terminal projection 的嚴格 API view。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HistoricalCompletionAlertView(_StrictModel):
    code: str = Field(min_length=1, max_length=191)
    owner: Literal["orders", "scheduling", "client_finance", "staff_payables"]
    field_path: str = Field(min_length=1, max_length=191)
    referral: Literal[
        "orders.completion",
        "orders.actual_start",
        "scheduling.official_service_facts",
        "client_finance.settlement",
        "staff_payables.payout",
    ]
    message: str = Field(min_length=1, max_length=191)


class HistoricalCompletionOwnerVersionView(_StrictModel):
    owner: Literal["orders", "client_finance"]
    version: str = Field(pattern=r"^(0|[1-9][0-9]*)$")


class HistoricalCompletionSourceVersionView(_StrictModel):
    kind: Literal[
        "payroll_case_account",
        "staff_obligation",
        "staff_obligation_event",
        "staff_payable_account",
        "staff_payable_projection",
        "staff_payout_event",
        "staff_payout_return_event",
        "staff_payout_reversal_event",
        "staff_payout_allocation",
        "staff_bank_fact",
        "staff_overpayment_recovery",
        "staff_overpayment_recovery_event",
    ]
    identity: str = Field(min_length=1, max_length=191)
    version: str = Field(pattern=r"^(0|[1-9][0-9]*)$")


class HistoricalCompletionView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    state: Literal["completed", "blocked", "unavailable"]
    step_11_status: Literal["completed", "blocked", "unavailable"]
    step_11_completed: StrictBool
    historical_alerts_completed: StrictBool
    active_alerts: list[HistoricalCompletionAlertView]
    owner_versions: list[HistoricalCompletionOwnerVersionView]
    owner_source_versions: list[HistoricalCompletionSourceVersionView]
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


__all__ = ["HistoricalCompletionView"]
