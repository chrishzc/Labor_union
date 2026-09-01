"""Staff Payables rules for adopted historical payout evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer, require_positive_integer


class HistoricalStaffConfirmationKind(StrEnum):
    PAID = "paid"
    SETTLED = "settled"


class HistoricalStaffSourceAvailability(StrEnum):
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    UNRECOVERABLE = "unrecoverable"


@dataclass(frozen=True, slots=True)
class HistoricalStaffPayoutIntent:
    case_no: str
    staff_id: int
    confirmation_kind: HistoricalStaffConfirmationKind
    obligation_identities: tuple[str, ...]
    payment_date: date | None
    payment_date_unknown_reason: str | None
    source_availability: HistoricalStaffSourceAvailability
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.staff_id, "staff id")
        _identities(self.obligation_identities)
        if (self.payment_date is None) == (self.payment_date_unknown_reason is None):
            raise ValueError("historical_staff_payout_date_shape_invalid")
        if self.payment_date_unknown_reason is not None:
            require_canonical_text(self.payment_date_unknown_reason, "payment date unknown reason", 500)
        if self.evidence_reference is not None:
            require_canonical_text(self.evidence_reference, "evidence reference", 191)


@dataclass(frozen=True, slots=True)
class HistoricalStaffObligation:
    identity: str
    case_no: str
    staff_id: int
    amount_due_ntd: int
    payroll_version: int
    direction: str
    status: str

    def __post_init__(self) -> None:
        require_canonical_text(self.identity, "obligation identity", 191)
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.staff_id, "staff id")
        require_positive_integer(self.amount_due_ntd, "obligation amount")
        require_nonnegative_integer(self.payroll_version, "obligation payroll version")
        if self.direction != "payable_to_staff":
            raise ValueError("historical_staff_obligation_direction_invalid")
        if self.status not in {"open", "settled", "cancelled"}:
            raise ValueError("historical_staff_obligation_status_invalid")


@dataclass(frozen=True, slots=True)
class HistoricalStaffPayoutFacts:
    case_no: str
    staff_id: int
    staff_payables_version: int
    adoption_receipt_id: int | None
    adopted: bool
    normal_bank_candidate_identities: tuple[str, ...]
    obligations: tuple[HistoricalStaffObligation, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.staff_id, "staff id")
        require_nonnegative_integer(self.staff_payables_version, "staff payables version")
        if self.adoption_receipt_id is not None:
            require_positive_integer(self.adoption_receipt_id, "adoption receipt id")
        if self.adopted != (self.adoption_receipt_id is not None):
            raise ValueError("historical_staff_adoption_shape_invalid")
        if self.normal_bank_candidate_identities:
            _identities(self.normal_bank_candidate_identities)


@dataclass(frozen=True, slots=True)
class HistoricalStaffPayoutCandidate:
    intent: HistoricalStaffPayoutIntent
    staff_payables_version: int
    adoption_receipt_id: int | None
    obligations: tuple[HistoricalStaffObligation, ...]
    amount_snapshot_ntd: int
    blockers: tuple[str, ...]
    fingerprint: PreviewFingerprint

    @property
    def can_apply(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class HistoricalStaffPayoutProjection:
    obligation_identity: str
    amount_snapshot_ntd: int
    obligation_payroll_version: int


def build_historical_staff_payout_candidate(
    facts: HistoricalStaffPayoutFacts,
    intent: HistoricalStaffPayoutIntent,
) -> HistoricalStaffPayoutCandidate:
    blockers: set[str] = set()
    if facts.case_no != intent.case_no:
        blockers.add("historical_staff_cross_case_forbidden")
    if facts.staff_id != intent.staff_id:
        blockers.add("historical_staff_cross_staff_forbidden")
    if not facts.adopted:
        blockers.add("historical_staff_case_not_adopted")
    if facts.normal_bank_candidate_identities:
        blockers.add("historical_staff_bank_reconciliation_required")

    by_identity = {item.identity: item for item in facts.obligations}
    selected = tuple(by_identity[item] for item in intent.obligation_identities if item in by_identity)
    if len(selected) != len(intent.obligation_identities):
        blockers.add("historical_staff_obligation_not_found")
    for obligation in selected:
        if obligation.case_no != intent.case_no:
            blockers.add("historical_staff_cross_case_forbidden")
        if obligation.staff_id != intent.staff_id:
            blockers.add("historical_staff_cross_staff_forbidden")
        if obligation.status != "open":
            blockers.add("historical_staff_obligation_not_open")
        if obligation.direction != "payable_to_staff":
            blockers.add("historical_staff_direction_mismatch")

    canonical = tuple(sorted(selected, key=lambda item: item.identity))
    payload = {
        "intent": _intent_payload(intent),
        "staff_payables_version": facts.staff_payables_version,
        "adoption_receipt_id": facts.adoption_receipt_id,
        "normal_bank_candidates": facts.normal_bank_candidate_identities,
        "obligations": tuple(
            {
                "identity": item.identity,
                "case_no": item.case_no,
                "staff_id": item.staff_id,
                "amount_ntd": item.amount_due_ntd,
                "payroll_version": item.payroll_version,
                "direction": item.direction,
                "status": item.status,
            }
            for item in canonical
        ),
        "blockers": tuple(sorted(blockers)),
    }
    return HistoricalStaffPayoutCandidate(
        intent,
        facts.staff_payables_version,
        facts.adoption_receipt_id,
        canonical,
        sum(item.amount_due_ntd for item in canonical),
        tuple(sorted(blockers)),
        fingerprint_payload(payload),
    )


def historical_staff_owner_is_terminal(
    obligations: tuple[HistoricalStaffObligation, ...],
    projections: tuple[HistoricalStaffPayoutProjection, ...],
) -> bool:
    by_identity = {item.obligation_identity: item for item in projections}
    for obligation in obligations:
        if obligation.status in {"settled", "cancelled"}:
            continue
        projection = by_identity.get(obligation.identity)
        if projection is None:
            return False
        if (
            projection.amount_snapshot_ntd != obligation.amount_due_ntd
            or projection.obligation_payroll_version != obligation.payroll_version
        ):
            return False
    return bool(obligations)


def _identities(values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple) or not values or values != tuple(sorted(set(values))):
        raise ValueError("historical_staff_obligation_identities_invalid")
    for value in values:
        require_canonical_text(value, "identity", 191)


def _intent_payload(intent: HistoricalStaffPayoutIntent) -> dict[str, object]:
    return {
        "case_no": intent.case_no,
        "staff_id": intent.staff_id,
        "confirmation_kind": intent.confirmation_kind.value,
        "obligation_identities": intent.obligation_identities,
        "payment_date": intent.payment_date.isoformat() if intent.payment_date else None,
        "payment_date_unknown_reason": intent.payment_date_unknown_reason,
        "source_availability": intent.source_availability.value,
        "evidence_reference": intent.evidence_reference,
    }


__all__ = [name for name in globals() if name.startswith("Historical") or name.startswith("build_") or name.startswith("historical_")]
