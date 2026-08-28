"""
File: client_refund_reversal.py
Description: Client Finance refund、recovery 與 reversal 的 strict HTTP contracts。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientRefundPreviewBody(_StrictModel):
    finance_import_row_ids: list[int] = Field(min_length=1)
    obligation_identities: list[str] = Field(min_length=1)
    allow_partial_refund_recovery: bool = False


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


class ClientOverRefundRecoveryPreviewBody(_StrictModel):
    recovery_identity: str = Field(min_length=1, max_length=191)
    finance_import_row_id: int = Field(gt=0)


class ClientOverRefundRecoveryApplyBody(ClientOverRefundRecoveryPreviewBody):
    expected_recovery_version: int = Field(ge=0)
    expected_account_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class ClientOverRefundRecoveryMatchedPreviewBody(ClientOverRefundRecoveryPreviewBody):
    matching_identity: str = Field(min_length=1, max_length=191)
    matching_version: int = Field(ge=1)
    evidence_reference: str = Field(min_length=1, max_length=500)


class ClientOverRefundRecoveryMatchedApplyBody(
    ClientOverRefundRecoveryMatchedPreviewBody
):
    expected_recovery_version: int = Field(ge=0)
    expected_account_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class ClientOverRefundRecoveryAdjustmentPreviewBody(_StrictModel):
    recovery_identity: str = Field(min_length=1, max_length=191)
    adjustment_amount_ntd: int = Field(gt=0)
    evidence_reference: str = Field(min_length=1, max_length=500)


class ClientOverRefundRecoveryAdjustmentApplyBody(
    ClientOverRefundRecoveryAdjustmentPreviewBody
):
    expected_recovery_version: int = Field(ge=0)
    expected_account_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class ClientOverRefundRecoveryMatchingPreviewBody(_StrictModel):
    recovery_identity: str = Field(min_length=1, max_length=191)
    finance_import_row_id: int = Field(gt=0)
    evidence_reference: str = Field(min_length=1, max_length=500)


class ClientOverRefundRecoveryMatchingApplyBody(
    ClientOverRefundRecoveryMatchingPreviewBody
):
    expected_recovery_version: int = Field(ge=0)
    expected_account_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class ClientOverRefundRecoveryPreviewView(_StrictModel):
    recovery_identity: str
    account_version: int = Field(ge=0)
    recovery_version: int = Field(ge=0)
    amount_received_ntd: int = Field(gt=0)
    remaining_before_ntd: int = Field(gt=0)
    remaining_after_ntd: int = Field(ge=0)
    resulting_status: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClientOverRefundRecoveryReceiptView(_StrictModel):
    recovery_identity: str
    account_version: int = Field(ge=0)
    recovery_version: int = Field(ge=0)
    remaining_after_ntd: int = Field(ge=0)
    resulting_status: str
    evidence_reference: str | None = None


class ClientOverRefundRecoveryAdjustmentPreviewView(_StrictModel):
    recovery_identity: str
    account_version: int = Field(ge=0)
    recovery_version: int = Field(ge=0)
    adjustment_amount_ntd: int = Field(gt=0)
    remaining_before_ntd: int = Field(gt=0)
    remaining_after_ntd: int = Field(ge=0)
    resulting_status: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClientOverRefundRecoveryMatchingPreviewView(_StrictModel):
    recovery_identity: str
    finance_import_row_identity: str
    recovery_version: int = Field(ge=0)
    account_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ClientOverRefundRecoveryMatchingReceiptView(_StrictModel):
    matching_identity: str
    matching_version: int = Field(ge=1)
    recovery_identity: str
    finance_import_row_identity: str
    recovery_version: int = Field(ge=0)
    account_version: int = Field(ge=0)
    evidence_reference: str | None = None


class ClientOverRefundRecoveryMatchingQueryView(_StrictModel):
    matching_identity: str = Field(min_length=1, max_length=191)
    matching_version: int = Field(ge=1)
    incoming_row_reference: str = Field(min_length=1, max_length=191)


class ClientOverRefundRecoveryQueryView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=191)
    recovery_identity: str = Field(min_length=1, max_length=191)
    remaining_amount_ntd: int = Field(ge=0)
    status: Literal["open", "partially_recovered", "recovered", "adjusted"]
    recovery_version: int = Field(ge=0)
    account_version: int = Field(ge=0)
    source_row_reference: str = Field(min_length=1, max_length=191)
    current_matchings: list[ClientOverRefundRecoveryMatchingQueryView]


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


class ClientPayableObligationView(_StrictModel):
    obligation_identity: str = Field(min_length=1, max_length=191)
    obligation_type: Literal["adjustment", "refund", "subsidy_return"]
    amount_due_ntd: int = Field(gt=0)
    due_date: date | None = None


class ClientOutgoingBankFactView(_StrictModel):
    finance_import_row_id: int = Field(gt=0)
    amount_ntd: int = Field(gt=0)
    transaction_date: date
    eligible_obligation_identities: list[str] = Field(min_length=1)


class ClientRefundReversalQueryView(_StrictModel):
    case_no: str
    account_version: int = Field(ge=0)
    refund_obligations: list[ClientPayableObligationView]
    subsidy_return_obligations: list[ClientPayableObligationView]
    refund_bank_facts: list[ClientOutgoingBankFactView]
    subsidy_return_bank_facts: list[ClientOutgoingBankFactView]
    reversal_targets: list[dict[str, Any]]
    refund_return_targets: list[dict[str, Any]]


class ClientSettlementReceivableObligationView(_StrictModel):
    obligation_identity: str = Field(min_length=1, max_length=191)
    payment_stage: Literal["deposit", "first", "second", "adjustment"]
    amount_due_ntd: int = Field(gt=0)
    due_date: date


class ClientSettlementIncomingBankFactView(_StrictModel):
    finance_import_row_id: int = Field(gt=0)
    amount_ntd: int = Field(gt=0)
    transaction_date: date


class ClientSettlementRemediationQueryView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=191)
    account_version: int = Field(ge=0)
    as_of: date
    receivable_obligations: list[ClientSettlementReceivableObligationView]
    refund_obligations: list[ClientPayableObligationView]
    subsidy_return_obligations: list[ClientPayableObligationView]
    incoming_bank_facts: list[ClientSettlementIncomingBankFactView]
    refund_bank_facts: list[ClientOutgoingBankFactView]
    subsidy_return_bank_facts: list[ClientOutgoingBankFactView]


__all__ = [
    "ClientRefundApplyBody",
    "ClientRefundPreviewBody",
    "ClientRefundReversalPreviewView",
    "ClientRefundReversalQueryView",
    "ClientRefundReversalReceiptView",
    "ClientSettlementRemediationQueryView",
    "ClientRefundReturnApplyBody",
    "ClientRefundReturnPreviewBody",
    "ClientOverRefundRecoveryApplyBody",
    "ClientOverRefundRecoveryMatchedApplyBody",
    "ClientOverRefundRecoveryMatchedPreviewBody",
    "ClientOverRefundRecoveryAdjustmentApplyBody",
    "ClientOverRefundRecoveryAdjustmentPreviewBody",
    "ClientOverRefundRecoveryAdjustmentPreviewView",
    "ClientOverRefundRecoveryMatchingApplyBody",
    "ClientOverRefundRecoveryMatchingPreviewBody",
    "ClientOverRefundRecoveryMatchingPreviewView",
    "ClientOverRefundRecoveryMatchingReceiptView",
    "ClientOverRefundRecoveryMatchingQueryView",
    "ClientOverRefundRecoveryQueryView",
    "ClientOverRefundRecoveryPreviewBody",
    "ClientOverRefundRecoveryPreviewView",
    "ClientOverRefundRecoveryReceiptView",
    "ClientReversalApplyBody",
    "ClientReversalPreviewBody",
]
