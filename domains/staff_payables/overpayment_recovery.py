"""Pure settlement rules for a staff payout overpayment recovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

_IDENTITY_MAXIMUM_LENGTH = 191


@dataclass(frozen=True, slots=True)
class PayrollCorrectionRecoverySource:
    """Exact Payroll correction lineage for a Staff Payables recovery root."""

    correction_identity: str
    case_no: str
    obligation_identity: str
    staff_id: int
    amount: MoneyNTD

    def __post_init__(self) -> None:
        require_canonical_text(self.correction_identity, "payroll correction identity", _IDENTITY_MAXIMUM_LENGTH)
        require_canonical_text(self.case_no, "case number", _IDENTITY_MAXIMUM_LENGTH)
        require_canonical_text(self.obligation_identity, "obligation identity", _IDENTITY_MAXIMUM_LENGTH)
        if not isinstance(self.staff_id, int) or self.staff_id <= 0:
            raise ValueError("staff_overpayment_recovery_target_ambiguous")
        if not isinstance(self.amount, MoneyNTD) or self.amount.amount <= 0:
            raise ValueError("staff_overpayment_recovery_amount_invalid")


class StaffOverpaymentRecoveryStatus(StrEnum):
    OPEN = "open"
    PARTIALLY_RECOVERED = "partially_recovered"
    RECOVERED = "recovered"
    ADJUSTED = "adjusted"


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecovery:
    identity: str
    staff_id: int
    remaining_amount: MoneyNTD
    status: StaffOverpaymentRecoveryStatus
    version: int

    def __post_init__(self) -> None:
        require_canonical_text(self.identity, "staff recovery identity", _IDENTITY_MAXIMUM_LENGTH)
        if not isinstance(self.staff_id, int) or self.staff_id <= 0:
            raise ValueError("staff_overpayment_recovery_target_ambiguous")
        if not isinstance(self.remaining_amount, MoneyNTD) or self.remaining_amount.amount <= 0:
            raise ValueError("staff_overpayment_recovery_not_open")
        if self.status not in {
            StaffOverpaymentRecoveryStatus.OPEN,
            StaffOverpaymentRecoveryStatus.PARTIALLY_RECOVERED,
        }:
            raise ValueError("staff_overpayment_recovery_not_open")
        require_nonnegative_integer(self.version, "staff recovery version")


@dataclass(frozen=True, slots=True)
class StaffRecoveryIncomingBankFact:
    identity: str
    staff_id: int
    amount: MoneyNTD
    occurred_on: str
    eligible: bool

    def __post_init__(self) -> None:
        require_canonical_text(self.identity, "incoming bank fact identity", _IDENTITY_MAXIMUM_LENGTH)
        require_canonical_text(self.occurred_on, "incoming bank occurred date", _IDENTITY_MAXIMUM_LENGTH)
        if not isinstance(self.staff_id, int) or self.staff_id <= 0:
            raise ValueError("staff_overpayment_recovery_target_ambiguous")
        if not isinstance(self.amount, MoneyNTD) or self.amount.amount <= 0:
            raise ValueError("staff_overpayment_recovery_amount_invalid")


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryCollectionCandidate:
    recovery_identity: str
    staff_id: int
    bank_fact_identity: str
    received_amount: MoneyNTD
    remaining_before: MoneyNTD
    remaining_after: MoneyNTD
    resulting_status: StaffOverpaymentRecoveryStatus
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryAdjustmentCandidate:
    recovery_identity: str
    staff_id: int
    adjusted_amount: MoneyNTD
    remaining_before: MoneyNTD
    resulting_status: StaffOverpaymentRecoveryStatus
    fingerprint: PreviewFingerprint


def build_staff_overpayment_recovery_collection_candidate(
    recovery: StaffOverpaymentRecovery,
    bank_fact: StaffRecoveryIncomingBankFact,
) -> StaffOverpaymentRecoveryCollectionCandidate:
    _require_collection_bank_fact(recovery, bank_fact)
    remaining_after = MoneyNTD(recovery.remaining_amount.amount - bank_fact.amount.amount)
    status = _collection_status(remaining_after)
    return StaffOverpaymentRecoveryCollectionCandidate(
        recovery.identity, recovery.staff_id, bank_fact.identity, bank_fact.amount,
        recovery.remaining_amount, remaining_after, status,
        fingerprint_payload(_collection_payload(recovery, bank_fact, remaining_after, status)),
    )


def build_staff_overpayment_recovery_adjustment_candidate(
    recovery: StaffOverpaymentRecovery,
    adjustment_amount: MoneyNTD,
    *,
    adjustment_authorized: bool,
) -> StaffOverpaymentRecoveryAdjustmentCandidate:
    if not adjustment_authorized:
        raise ValueError("staff_overpayment_recovery_adjustment_forbidden")
    if adjustment_amount != recovery.remaining_amount:
        raise ValueError("staff_overpayment_recovery_adjustment_amount_invalid")
    return StaffOverpaymentRecoveryAdjustmentCandidate(
        recovery.identity, recovery.staff_id, adjustment_amount, recovery.remaining_amount,
        StaffOverpaymentRecoveryStatus.ADJUSTED,
        fingerprint_payload(_adjustment_payload(recovery, adjustment_amount)),
    )


def _require_collection_bank_fact(recovery, bank_fact) -> None:
    if recovery.staff_id != bank_fact.staff_id:
        raise ValueError("staff_overpayment_recovery_target_ambiguous")
    if not bank_fact.eligible:
        raise ValueError("bank_fact_not_eligible")
    if bank_fact.amount.amount > recovery.remaining_amount.amount:
        raise ValueError("staff_overpayment_recovery_amount_exceeded")


def _collection_status(remaining_after):
    if remaining_after.amount == 0:
        return StaffOverpaymentRecoveryStatus.RECOVERED
    return StaffOverpaymentRecoveryStatus.PARTIALLY_RECOVERED


def _collection_payload(recovery, bank_fact, remaining_after, status):
    return {
        "recovery_identity": recovery.identity,
        "recovery_version": recovery.version,
        "staff_id": recovery.staff_id,
        "bank_fact_identity": bank_fact.identity,
        "received_amount_ntd": bank_fact.amount.amount,
        "remaining_before_ntd": recovery.remaining_amount.amount,
        "remaining_after_ntd": remaining_after.amount,
        "resulting_status": status.value,
    }


def _adjustment_payload(recovery, adjustment_amount):
    return {
        "recovery_identity": recovery.identity,
        "recovery_version": recovery.version,
        "staff_id": recovery.staff_id,
        "adjusted_amount_ntd": adjustment_amount.amount,
        "resulting_status": StaffOverpaymentRecoveryStatus.ADJUSTED.value,
    }


__all__ = [name for name in globals() if name.startswith("StaffOverpayment") or name.startswith("StaffRecovery") or name.startswith("PayrollCorrection") or name.startswith("build_staff")]
