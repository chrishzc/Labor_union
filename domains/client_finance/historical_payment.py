"""Client Finance rules for adopted historical payment evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)


class HistoricalClientDirection(StrEnum):
    RECEIVABLE_FROM_CLIENT = "receivable_from_client"
    PAYABLE_TO_CLIENT = "payable_to_client"


class HistoricalClientConfirmationKind(StrEnum):
    PAID = "paid"
    SETTLED = "settled"


class HistoricalClientSourceAvailability(StrEnum):
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    UNRECOVERABLE = "unrecoverable"


@dataclass(frozen=True, slots=True)
class HistoricalClientPaymentIntent:
    case_no: str
    direction: HistoricalClientDirection
    confirmation_kind: HistoricalClientConfirmationKind
    obligation_identities: tuple[str, ...]
    payment_date: date | None
    payment_date_unknown_reason: str | None
    source_availability: HistoricalClientSourceAvailability
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        _identities(self.obligation_identities)
        if (self.payment_date is None) == (self.payment_date_unknown_reason is None):
            raise ValueError("historical_client_payment_date_shape_invalid")
        if self.payment_date_unknown_reason is not None:
            require_canonical_text(
                self.payment_date_unknown_reason,
                "payment date unknown reason",
                500,
            )
        if self.evidence_reference is not None:
            require_canonical_text(self.evidence_reference, "evidence reference", 191)


@dataclass(frozen=True, slots=True)
class HistoricalClientObligation:
    identity: str
    case_no: str
    obligation_type: str
    direction: HistoricalClientDirection
    amount_due_ntd: int
    projection_version: int
    status: str

    def __post_init__(self) -> None:
        require_canonical_text(self.identity, "obligation identity", 191)
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(self.obligation_type, "obligation type", 50)
        require_positive_integer(self.amount_due_ntd, "obligation amount")
        require_nonnegative_integer(self.projection_version, "obligation projection version")
        if self.status not in {"open", "settled", "cancelled"}:
            raise ValueError("historical_client_obligation_status_invalid")


@dataclass(frozen=True, slots=True)
class HistoricalClientPaymentFacts:
    case_no: str
    account_version: int
    adoption_receipt_id: int | None
    adopted: bool
    normal_bank_candidate_identities: tuple[str, ...]
    obligations: tuple[HistoricalClientObligation, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_nonnegative_integer(self.account_version, "client account version")
        if self.adoption_receipt_id is not None:
            require_positive_integer(self.adoption_receipt_id, "adoption receipt id")
        if self.adopted != (self.adoption_receipt_id is not None):
            raise ValueError("historical_client_adoption_shape_invalid")
        if self.normal_bank_candidate_identities:
            _identities(self.normal_bank_candidate_identities)


@dataclass(frozen=True, slots=True)
class HistoricalClientPaymentCandidate:
    intent: HistoricalClientPaymentIntent
    account_version: int
    adoption_receipt_id: int | None
    obligations: tuple[HistoricalClientObligation, ...]
    amount_snapshot_ntd: int
    blockers: tuple[str, ...]
    fingerprint: PreviewFingerprint

    @property
    def can_apply(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class HistoricalClientPaymentProjection:
    obligation_identity: str
    amount_snapshot_ntd: int
    obligation_projection_version: int


def build_historical_client_payment_candidate(
    facts: HistoricalClientPaymentFacts,
    intent: HistoricalClientPaymentIntent,
) -> HistoricalClientPaymentCandidate:
    blockers: set[str] = set()
    if facts.case_no != intent.case_no:
        blockers.add("historical_client_cross_case_forbidden")
    if not facts.adopted:
        blockers.add("historical_client_case_not_adopted")
    if facts.normal_bank_candidate_identities:
        blockers.add("historical_client_bank_reconciliation_required")

    by_identity = {item.identity: item for item in facts.obligations}
    selected = tuple(
        by_identity[identity]
        for identity in intent.obligation_identities
        if identity in by_identity
    )
    if len(selected) != len(intent.obligation_identities):
        blockers.add("historical_client_obligation_not_found")
    allowed_types = (
        {"deposit", "first", "second", "adjustment"}
        if intent.direction is HistoricalClientDirection.RECEIVABLE_FROM_CLIENT
        else {"refund", "subsidy_return", "adjustment"}
    )
    for obligation in selected:
        if obligation.case_no != intent.case_no:
            blockers.add("historical_client_cross_case_forbidden")
        if obligation.status != "open":
            blockers.add("historical_client_obligation_not_open")
        if obligation.direction is not intent.direction:
            blockers.add("historical_client_direction_mismatch")
        if obligation.obligation_type not in allowed_types:
            blockers.add("historical_client_obligation_type_mismatch")

    canonical_obligations = tuple(sorted(selected, key=lambda item: item.identity))
    payload = {
        "intent": _intent_payload(intent),
        "account_version": facts.account_version,
        "adoption_receipt_id": facts.adoption_receipt_id,
        "normal_bank_candidates": facts.normal_bank_candidate_identities,
        "obligations": tuple(
            {
                "identity": item.identity,
                "case_no": item.case_no,
                "type": item.obligation_type,
                "direction": item.direction.value,
                "amount_ntd": item.amount_due_ntd,
                "projection_version": item.projection_version,
                "status": item.status,
            }
            for item in canonical_obligations
        ),
        "blockers": tuple(sorted(blockers)),
    }
    return HistoricalClientPaymentCandidate(
        intent,
        facts.account_version,
        facts.adoption_receipt_id,
        canonical_obligations,
        sum(item.amount_due_ntd for item in canonical_obligations),
        tuple(sorted(blockers)),
        fingerprint_payload(payload),
    )


def historical_client_owner_is_terminal(
    obligations: tuple[HistoricalClientObligation, ...],
    projections: tuple[HistoricalClientPaymentProjection, ...],
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
            or projection.obligation_projection_version != obligation.projection_version
        ):
            return False
    return bool(obligations)


def _identities(values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple) or not values or values != tuple(sorted(set(values))):
        raise ValueError("historical_client_obligation_identities_invalid")
    for value in values:
        require_canonical_text(value, "identity", 191)


def _intent_payload(intent: HistoricalClientPaymentIntent) -> dict[str, object]:
    return {
        "case_no": intent.case_no,
        "direction": intent.direction.value,
        "confirmation_kind": intent.confirmation_kind.value,
        "obligation_identities": intent.obligation_identities,
        "payment_date": intent.payment_date.isoformat() if intent.payment_date else None,
        "payment_date_unknown_reason": intent.payment_date_unknown_reason,
        "source_availability": intent.source_availability.value,
        "evidence_reference": intent.evidence_reference,
    }


__all__ = [name for name in globals() if name.startswith("Historical") or name.startswith("build_") or name.startswith("historical_")]
