"""Pure contracts for the PAYOUT-002 late Payroll obligation decision.

PAYOUT-002 belongs to Payroll: a late source event is first reconciled with
the legal obligation.  Staff Payables only receives a separate recovery root
when money was actually paid above that corrected legal amount.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191


class LateObligationDisposition(StrEnum):
    """The only outcomes a reviewed late source may produce."""

    INCREASE_OBLIGATION = "increase_obligation"
    REDUCE_UNPAID_OBLIGATION = "reduce_unpaid_obligation"
    CORRECT_PAID_OBLIGATION = "correct_paid_obligation"
    REVIEWED_NO_CHANGE = "reviewed_no_change"


class PayrollDispositionPersistenceKind(StrEnum):
    """Persisted Payroll meaning, independent of Staff Payables recovery."""

    APPEND_INCREASE = "append_increase"
    APPEND_UNPAID_REDUCTION = "append_unpaid_reduction"
    CORRECT_PAID_LEGAL_AMOUNT = "correct_paid_legal_amount"
    APPEND_REVIEWED_NO_CHANGE = "append_reviewed_no_change"


@dataclass(frozen=True, slots=True)
class LatePayrollObligationFacts:
    """Fresh, source-bound facts used by both Preview and Apply."""

    case_no: str
    obligation_identity: str
    source_event_identity: str
    assignment_id: int
    staff_id: int
    current_amount: MoneyNTD
    corrected_amount: MoneyNTD
    actual_paid_amount: MoneyNTD
    payroll_version: int
    obligation_version: int
    due_date: date
    source_event_at: datetime
    source_event_is_late: bool = True

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        for value, field_name in (
            (self.obligation_identity, "obligation identity"),
            (self.source_event_identity, "source event identity"),
        ):
            require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)
        require_positive_integer(self.assignment_id, "assignment id")
        require_positive_integer(self.staff_id, "staff id")
        for value, field_name in (
            (self.current_amount, "current obligation amount"),
            (self.corrected_amount, "corrected obligation amount"),
            (self.actual_paid_amount, "actual paid amount"),
        ):
            if not isinstance(value, MoneyNTD):
                raise TypeError(f"{field_name} must be MoneyNTD")
            require_nonnegative_integer(value.amount, field_name)
        require_nonnegative_integer(self.payroll_version, "payroll version")
        require_nonnegative_integer(self.obligation_version, "obligation version")
        if not isinstance(self.due_date, date) or isinstance(self.due_date, datetime):
            raise TypeError("obligation due date must be a date")
        if not isinstance(self.source_event_at, datetime) or self.source_event_at.tzinfo is None:
            raise ValueError("source event timestamp must be timezone aware")
        if not isinstance(self.source_event_is_late, bool):
            raise TypeError("source event late flag must be bool")
        if not self.source_event_is_late:
            raise ValueError("payout002_source_event_not_late")


@dataclass(frozen=True, slots=True)
class LatePayrollObligationIntent:
    """The reviewed correction target; the source event is never rewritten."""

    case_no: str
    obligation_identity: str
    source_event_identity: str
    corrected_amount: MoneyNTD

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(self.obligation_identity, "obligation identity", _IDENTITY_MAXIMUM_LENGTH)
        require_canonical_text(self.source_event_identity, "source event identity", _IDENTITY_MAXIMUM_LENGTH)
        if not isinstance(self.corrected_amount, MoneyNTD):
            raise TypeError("corrected obligation amount must be MoneyNTD")
        require_nonnegative_integer(self.corrected_amount.amount, "corrected obligation amount")


@dataclass(frozen=True, slots=True)
class LatePayrollObligationCandidate:
    case_no: str
    obligation_identity: str
    source_event_identity: str
    assignment_id: int
    staff_id: int
    current_amount: MoneyNTD
    corrected_amount: MoneyNTD
    actual_paid_amount: MoneyNTD
    delta_amount: MoneyNTD
    disposition: LateObligationDisposition
    correction_identity: str
    recovery_amount: MoneyNTD
    expected_payroll_version: int
    expected_obligation_version: int
    fingerprint: PreviewFingerprint

    @property
    def persistence_kind(self) -> PayrollDispositionPersistenceKind:
        return {
            LateObligationDisposition.INCREASE_OBLIGATION: PayrollDispositionPersistenceKind.APPEND_INCREASE,
            LateObligationDisposition.REDUCE_UNPAID_OBLIGATION: PayrollDispositionPersistenceKind.APPEND_UNPAID_REDUCTION,
            LateObligationDisposition.CORRECT_PAID_OBLIGATION: PayrollDispositionPersistenceKind.CORRECT_PAID_LEGAL_AMOUNT,
            LateObligationDisposition.REVIEWED_NO_CHANGE: PayrollDispositionPersistenceKind.APPEND_REVIEWED_NO_CHANGE,
        }[self.disposition]

    @property
    def creates_payroll_staff_receivable(self) -> bool:
        """Payroll never creates the Staff Payables recovery obligation."""

        return False

    @property
    def completion_predicate(self) -> str:
        return "payroll_late_obligation_disposition_complete"

    @property
    def delta(self) -> MoneyNTD:
        """Signed corrected-minus-current amount."""

        return self.delta_amount

    @property
    def actual_paid_excess(self) -> MoneyNTD:
        """Amount Staff Payables may open as an overpayment recovery."""

        return self.recovery_amount

    @property
    def requires_staff_overpayment_recovery(self) -> bool:
        return self.recovery_amount.amount > 0


def build_late_payroll_obligation_candidate(
    facts: LatePayrollObligationFacts,
    intent: LatePayrollObligationIntent,
) -> LatePayrollObligationCandidate:
    """Build the signed delta and its mutually exclusive consequence."""

    if facts.case_no != intent.case_no:
        raise ValueError("payout002_case_mismatch")
    if facts.obligation_identity != intent.obligation_identity:
        raise ValueError("payout002_obligation_mismatch")
    if facts.source_event_identity != intent.source_event_identity:
        raise ValueError("payout002_source_event_mismatch")

    delta = intent.corrected_amount.amount - facts.current_amount.amount
    delta_money = MoneyNTD(delta)
    if delta > 0:
        disposition = LateObligationDisposition.INCREASE_OBLIGATION
    elif delta < 0 and facts.actual_paid_amount.amount == 0:
        disposition = LateObligationDisposition.REDUCE_UNPAID_OBLIGATION
    elif delta < 0:
        disposition = LateObligationDisposition.CORRECT_PAID_OBLIGATION
    else:
        disposition = LateObligationDisposition.REVIEWED_NO_CHANGE

    # Staff Payables recovery is a consequence only of a paid negative
    # correction.  A positive or zero-delta review never opens recovery,
    # even if historical paid totals happen to exceed the reviewed amount.
    recovery = (
        max(facts.actual_paid_amount.amount - intent.corrected_amount.amount, 0)
        if disposition is LateObligationDisposition.CORRECT_PAID_OBLIGATION
        else 0
    )
    identity = "payroll-late-correction:" + fingerprint_payload(
        {
            "case_no": facts.case_no,
            "obligation_identity": facts.obligation_identity,
            "source_event_identity": facts.source_event_identity,
            "corrected_amount_ntd": intent.corrected_amount.amount,
        }
    ).value[:32]
    payload = {
        "case_no": facts.case_no,
        "obligation_identity": facts.obligation_identity,
        "source_event_identity": facts.source_event_identity,
        "assignment_id": facts.assignment_id,
        "staff_id": facts.staff_id,
        "current_amount_ntd": facts.current_amount.amount,
        "corrected_amount_ntd": intent.corrected_amount.amount,
        "actual_paid_amount_ntd": facts.actual_paid_amount.amount,
        "delta_amount_ntd": delta,
        "disposition": disposition.value,
        "recovery_amount_ntd": recovery,
        "payroll_version": facts.payroll_version,
        "obligation_version": facts.obligation_version,
    }
    return LatePayrollObligationCandidate(
        facts.case_no,
        facts.obligation_identity,
        facts.source_event_identity,
        facts.assignment_id,
        facts.staff_id,
        facts.current_amount,
        intent.corrected_amount,
        facts.actual_paid_amount,
        delta_money,
        disposition,
        identity,
        MoneyNTD(recovery),
        facts.payroll_version,
        facts.obligation_version,
        fingerprint_payload(payload),
    )


def late_obligation_completion_matches(
    candidate: LatePayrollObligationCandidate,
    readback: LatePayrollObligationFacts,
) -> bool:
    """Check the terminal predicate against a fresh owner readback."""

    if readback.case_no != candidate.case_no:
        return False
    if readback.obligation_identity != candidate.obligation_identity:
        return False
    if readback.source_event_identity != candidate.source_event_identity:
        return False
    if readback.payroll_version != candidate.expected_payroll_version + 1:
        return False
    if readback.obligation_version <= candidate.expected_obligation_version:
        return False
    if readback.corrected_amount != candidate.corrected_amount:
        return False
    if candidate.disposition is LateObligationDisposition.REVIEWED_NO_CHANGE:
        return readback.current_amount == candidate.current_amount
    return readback.current_amount == candidate.corrected_amount


PayrollLateObligationFacts = LatePayrollObligationFacts
PayrollLateObligationIntent = LatePayrollObligationIntent
PayrollLateObligationCandidate = LatePayrollObligationCandidate


__all__ = [
    "LateObligationDisposition",
    "PayrollDispositionPersistenceKind",
    "LatePayrollObligationCandidate",
    "LatePayrollObligationFacts",
    "LatePayrollObligationIntent",
    "PayrollLateObligationCandidate",
    "PayrollLateObligationFacts",
    "PayrollLateObligationIntent",
    "build_late_payroll_obligation_candidate",
    "late_obligation_completion_matches",
]
