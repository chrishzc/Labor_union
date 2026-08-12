"""Pure rules for collecting a client refund overpayment recovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

_IDENTITY_MAXIMUM_LENGTH = 191


class ClientOverRefundRecoveryStatus(StrEnum):
    OPEN = "open"
    PARTIALLY_RECOVERED = "partially_recovered"
    RECOVERED = "recovered"
    ADJUSTED = "adjusted"


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecovery:
    identity: str
    case_no: str
    remaining_amount: MoneyNTD
    status: ClientOverRefundRecoveryStatus
    version: int

    def __post_init__(self) -> None:
        _require_identity(self.identity, "recovery identity")
        _require_identity(self.case_no, "case number")
        if not isinstance(self.remaining_amount, MoneyNTD) or self.remaining_amount.amount <= 0:
            raise ValueError("client_over_refund_recovery_not_open")
        if self.status not in {ClientOverRefundRecoveryStatus.OPEN, ClientOverRefundRecoveryStatus.PARTIALLY_RECOVERED}:
            raise ValueError("client_over_refund_recovery_not_open")
        require_nonnegative_integer(self.version, "recovery version")


@dataclass(frozen=True, slots=True)
class ClientRecoveryIncomingBankFact:
    identity: str
    case_no: str
    amount: MoneyNTD
    occurred_on: str
    eligible: bool

    def __post_init__(self) -> None:
        _require_identity(self.identity, "incoming bank fact identity")
        _require_identity(self.case_no, "case number")
        _require_identity(self.occurred_on, "incoming occurred date")
        if not isinstance(self.amount, MoneyNTD) or self.amount.amount <= 0:
            raise ValueError("client_over_refund_recovery_amount_invalid")


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryCandidate:
    recovery_identity: str
    case_no: str
    bank_fact_identity: str
    amount_received: MoneyNTD
    remaining_before: MoneyNTD
    remaining_after: MoneyNTD
    resulting_status: ClientOverRefundRecoveryStatus
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryAdjustmentCandidate:
    recovery_identity: str
    case_no: str
    adjustment_amount: MoneyNTD
    remaining_before: MoneyNTD
    remaining_after: MoneyNTD
    resulting_status: ClientOverRefundRecoveryStatus
    fingerprint: PreviewFingerprint


def build_client_over_refund_recovery_candidate(
    recovery: ClientOverRefundRecovery,
    bank_fact: ClientRecoveryIncomingBankFact,
) -> ClientOverRefundRecoveryCandidate:
    _require_matching_case(recovery, bank_fact)
    _require_eligible_bank_fact(bank_fact)
    _require_within_remaining(recovery, bank_fact)
    remaining_after = MoneyNTD(recovery.remaining_amount.amount - bank_fact.amount.amount)
    status = _resulting_status(remaining_after)
    return ClientOverRefundRecoveryCandidate(
        recovery.identity,
        recovery.case_no,
        bank_fact.identity,
        bank_fact.amount,
        recovery.remaining_amount,
        remaining_after,
        status,
        fingerprint_payload(_candidate_payload(recovery, bank_fact, remaining_after, status)),
    )


def build_client_over_refund_recovery_adjustment_candidate(
    recovery: ClientOverRefundRecovery,
    adjustment_amount: MoneyNTD,
    *,
    adjustment_authorized: bool,
) -> ClientOverRefundRecoveryAdjustmentCandidate:
    if not adjustment_authorized:
        raise ValueError("client_over_refund_recovery_adjustment_forbidden")
    if adjustment_amount.amount <= 0:
        raise ValueError("client_over_refund_recovery_amount_exceeded")
    if adjustment_amount.amount > recovery.remaining_amount.amount:
        raise ValueError("client_over_refund_recovery_amount_exceeded")
    remaining_after = MoneyNTD(
        recovery.remaining_amount.amount - adjustment_amount.amount
    )
    status = (
        ClientOverRefundRecoveryStatus.ADJUSTED
        if remaining_after.amount == 0
        else ClientOverRefundRecoveryStatus.OPEN
    )
    return ClientOverRefundRecoveryAdjustmentCandidate(
        recovery.identity,
        recovery.case_no,
        adjustment_amount,
        recovery.remaining_amount,
        remaining_after,
        status,
        fingerprint_payload(
            {
                "recovery_identity": recovery.identity,
                "case_no": recovery.case_no,
                "recovery_version": recovery.version,
                "adjustment_amount_ntd": adjustment_amount.amount,
                "remaining_before_ntd": recovery.remaining_amount.amount,
                "remaining_after_ntd": remaining_after.amount,
                "resulting_status": status.value,
            }
        ),
    )


def _require_matching_case(recovery, bank_fact) -> None:
    if recovery.case_no != bank_fact.case_no:
        raise ValueError("client_over_refund_recovery_target_ambiguous")


def _require_eligible_bank_fact(bank_fact) -> None:
    if not bank_fact.eligible:
        raise ValueError("bank_fact_not_eligible")


def _require_within_remaining(recovery, bank_fact) -> None:
    if bank_fact.amount.amount > recovery.remaining_amount.amount:
        raise ValueError("client_over_refund_recovery_amount_exceeded")


def _resulting_status(remaining_after):
    return (
        ClientOverRefundRecoveryStatus.RECOVERED
        if remaining_after.amount == 0
        else ClientOverRefundRecoveryStatus.PARTIALLY_RECOVERED
    )


def _candidate_payload(recovery, bank_fact, remaining_after, status):
    return {
        "recovery_identity": recovery.identity,
        "case_no": recovery.case_no,
        "recovery_version": recovery.version,
        "bank_fact_identity": bank_fact.identity,
        "amount_received_ntd": bank_fact.amount.amount,
        "remaining_before_ntd": recovery.remaining_amount.amount,
        "remaining_after_ntd": remaining_after.amount,
        "resulting_status": status.value,
    }


def _require_identity(value, label) -> None:
    require_canonical_text(value, label, _IDENTITY_MAXIMUM_LENGTH)


__all__ = [
    "ClientOverRefundRecovery",
    "ClientOverRefundRecoveryAdjustmentCandidate",
    "ClientOverRefundRecoveryCandidate",
    "ClientOverRefundRecoveryStatus",
    "ClientRecoveryIncomingBankFact",
    "build_client_over_refund_recovery_candidate",
    "build_client_over_refund_recovery_adjustment_candidate",
]
