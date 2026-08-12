"""Pure Government Subsidy overpayment disposition rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer
from domains.government_subsidy.ledger import (
    AllocationIntent,
    ClaimBatchFacts,
    GovernmentBankFact,
    GovernmentSubsidyBankDirection,
    reduce_batch_status,
)

_IDENTITY_MAXIMUM_LENGTH = 191


class GovernmentSubsidyOverpaymentStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    OFFSET_RESERVED = "offset_reserved"
    OFFSET_APPLIED = "offset_applied"
    RETURN_PAYABLE = "return_payable"
    PARTIALLY_RETURNED = "partially_returned"
    RETURNED = "returned"


class GovernmentSubsidyOverpaymentError(ValueError):
    """Stable business error for overpayment disposition commands."""


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyOverpayment:
    identity: str
    payer_identity: str
    remaining_amount_ntd: MoneyNTD
    status: GovernmentSubsidyOverpaymentStatus
    version: int

    def __post_init__(self) -> None:
        _require_text(self.identity, "overpayment identity")
        _require_text(self.payer_identity, "government payer identity")
        if not isinstance(self.remaining_amount_ntd, MoneyNTD):
            raise TypeError("overpayment amount must be MoneyNTD")
        if self.remaining_amount_ntd.amount < 0:
            raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_not_open")
        if (
            self.remaining_amount_ntd.amount == 0
            and self.status not in {
                GovernmentSubsidyOverpaymentStatus.OFFSET_APPLIED,
                GovernmentSubsidyOverpaymentStatus.RETURNED,
            }
        ):
            raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_not_open")
        if self.status not in {
            GovernmentSubsidyOverpaymentStatus.PENDING_REVIEW,
            GovernmentSubsidyOverpaymentStatus.OFFSET_RESERVED,
            GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE,
            GovernmentSubsidyOverpaymentStatus.PARTIALLY_RETURNED,
            GovernmentSubsidyOverpaymentStatus.OFFSET_APPLIED,
            GovernmentSubsidyOverpaymentStatus.RETURNED,
        }:
            raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_not_open")
        require_nonnegative_integer(self.version, "overpayment version")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyOffsetTarget:
    claim_item_id: int
    claim_batch_id: int
    batch_version: int
    batch_approved_amount_ntd: MoneyNTD
    batch_net_allocated_amount_ntd: MoneyNTD
    payer_identity: str
    outstanding_amount_ntd: MoneyNTD
    submitted: bool
    approved: bool

    def __post_init__(self) -> None:
        if self.claim_item_id <= 0 or self.claim_batch_id <= 0:
            raise ValueError("claim item and batch ids must be positive")
        require_nonnegative_integer(self.batch_version, "claim batch version")
        _require_text(self.payer_identity, "government payer identity")
        if not isinstance(self.outstanding_amount_ntd, MoneyNTD):
            raise TypeError("target outstanding amount must be MoneyNTD")
        if self.outstanding_amount_ntd.amount <= 0:
            raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_target_invalid")
        if self.batch_approved_amount_ntd.amount <= 0:
            raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_target_invalid")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyOffsetIntent:
    claim_item_id: int
    amount_ntd: MoneyNTD

    def __post_init__(self) -> None:
        if self.claim_item_id <= 0:
            raise ValueError("claim item id must be positive")
        if not isinstance(self.amount_ntd, MoneyNTD) or self.amount_ntd.amount <= 0:
            raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_amount_invalid")


@dataclass(frozen=True, slots=True)
class GovernmentRecipientSnapshot:
    agency_identity: str
    agency_name: str
    bank_code: str
    account_display: str
    account_fingerprint: str
    effective_date: str
    due_date: str
    evidence_reference: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.agency_identity, "agency identity"),
            (self.agency_name, "agency name"),
            (self.bank_code, "bank code"),
            (self.account_display, "masked account"),
            (self.account_fingerprint, "account fingerprint"),
            (self.effective_date, "effective date"),
            (self.due_date, "due date"),
            (self.evidence_reference, "evidence reference"),
        ):
            _require_text(value, label)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyOverpaymentCandidate:
    overpayment_identity: str
    overpayment_version: int
    remaining_before_ntd: MoneyNTD
    disposition_amount_ntd: MoneyNTD
    remaining_after_ntd: MoneyNTD
    resulting_status: GovernmentSubsidyOverpaymentStatus
    disposition_kind: str
    fingerprint: PreviewFingerprint
    offset_targets: tuple[GovernmentSubsidyOffsetTarget, ...] = ()


@dataclass(frozen=True, slots=True)
class GovernmentOverpaymentReturnReconciliationCandidate:
    payable_identity: str
    overpayment_identity: str
    overpayment_version: int
    bank_fact_identity: str
    amount_ntd: MoneyNTD
    remaining_after_ntd: MoneyNTD
    resulting_status: GovernmentSubsidyOverpaymentStatus
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReceiptWithOverageCandidate:
    batch_id: int
    expected_batch_version: int
    allocations: tuple[GovernmentSubsidyOffsetIntent, ...]
    allocated_amount_ntd: MoneyNTD
    overpayment_amount_ntd: MoneyNTD
    resulting_net_allocated_ntd: MoneyNTD
    resulting_outstanding_ntd: MoneyNTD
    resulting_batch_status: str
    fingerprint: PreviewFingerprint


def build_overpayment_offset_candidate(
    overpayment: GovernmentSubsidyOverpayment,
    targets: tuple[GovernmentSubsidyOffsetTarget, ...],
    intents: tuple[GovernmentSubsidyOffsetIntent, ...],
) -> GovernmentSubsidyOverpaymentCandidate:
    _require_offset_allowed(overpayment)
    intent_by_item = _unique_offset_intents(intents)
    target_by_item = {target.claim_item_id: target for target in targets}
    _validate_offset_targets(overpayment, target_by_item, intent_by_item)
    amount = _sum_money(intent.amount_ntd for intent in intents)
    _require_within_remaining(overpayment, amount)
    remaining = MoneyNTD(overpayment.remaining_amount_ntd.amount - amount.amount)
    status = (
        GovernmentSubsidyOverpaymentStatus.OFFSET_APPLIED
        if remaining.amount == 0
        else GovernmentSubsidyOverpaymentStatus.OFFSET_RESERVED
    )
    return _candidate(overpayment, amount, remaining, status, "offset", targets)


def build_receipt_with_overage_candidate(
    bank_fact: GovernmentBankFact,
    batch: ClaimBatchFacts,
    intents: tuple[GovernmentSubsidyOffsetIntent, ...],
) -> GovernmentSubsidyReceiptWithOverageCandidate:
    if bank_fact.direction is not GovernmentSubsidyBankDirection.INCOMING:
        raise GovernmentSubsidyOverpaymentError("government_subsidy_bank_fact_invalid")
    intent_by_item = _unique_offset_intents(intents)
    item_by_id = {item.item_id: item for item in batch.items}
    if set(intent_by_item) - set(item_by_id):
        raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_target_invalid")
    if not batch.submitted or not batch.approval_complete:
        raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_target_invalid")
    for item_id, intent in intent_by_item.items():
        if intent.amount_ntd.amount > item_by_id[item_id].outstanding_amount_ntd.amount:
            raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_amount_exceeded")
    allocated = _sum_money(intent.amount_ntd for intent in intents)
    if allocated.amount <= 0 or allocated.amount >= bank_fact.amount_ntd.amount:
        raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_amount_invalid")
    overpayment = MoneyNTD(bank_fact.amount_ntd.amount - allocated.amount)
    after_net = MoneyNTD(batch.net_allocated_total_ntd.amount + allocated.amount)
    after_status = reduce_batch_status(batch, after_net).value
    fingerprint = fingerprint_payload({
        "bank_fact_identity": bank_fact.bank_fact_identity,
        "batch_id": batch.batch_id,
        "batch_version": batch.aggregate_version,
        "allocations": _fingerprint_payload(intents),
        "overpayment_amount_ntd": overpayment.amount,
    })
    outstanding = MoneyNTD(batch.approved_total_ntd.amount - after_net.amount)
    return GovernmentSubsidyReceiptWithOverageCandidate(
        batch.batch_id, batch.aggregate_version, intents, allocated, overpayment,
        after_net, outstanding, after_status, fingerprint,
    )


def build_overpayment_return_candidate(
    overpayment: GovernmentSubsidyOverpayment,
    recipient: GovernmentRecipientSnapshot,
) -> GovernmentSubsidyOverpaymentCandidate:
    _require_return_allowed(overpayment)
    amount = overpayment.remaining_amount_ntd
    return _candidate(
        overpayment,
        amount,
        amount,
        GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE,
        "return",
        recipient,
    )


def build_overpayment_return_reconciliation_candidate(
    overpayment: GovernmentSubsidyOverpayment,
    payable_identity: str,
    payable_remaining_ntd: MoneyNTD,
    payable_version: int,
    bank_fact: GovernmentBankFact,
) -> GovernmentOverpaymentReturnReconciliationCandidate:
    if overpayment.status not in {
        GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE,
        GovernmentSubsidyOverpaymentStatus.PARTIALLY_RETURNED,
    }:
        raise GovernmentSubsidyOverpaymentError("government_overpayment_return_reconciliation_conflict")
    if bank_fact.direction is not GovernmentSubsidyBankDirection.OUTGOING:
        raise GovernmentSubsidyOverpaymentError("government_subsidy_bank_fact_invalid")
    if bank_fact.amount_ntd.amount > payable_remaining_ntd.amount:
        raise GovernmentSubsidyOverpaymentError("government_overpayment_return_outbound_amount_exceeded")
    remaining = MoneyNTD(payable_remaining_ntd.amount - bank_fact.amount_ntd.amount)
    status = (
        GovernmentSubsidyOverpaymentStatus.RETURNED
        if remaining.amount == 0
        else GovernmentSubsidyOverpaymentStatus.PARTIALLY_RETURNED
    )
    fingerprint = fingerprint_payload({
        "overpayment_identity": overpayment.identity,
        "overpayment_version": overpayment.version,
        "payable_identity": payable_identity,
        "payable_version": payable_version,
        "bank_fact_identity": bank_fact.bank_fact_identity,
        "amount_ntd": bank_fact.amount_ntd.amount,
    })
    return GovernmentOverpaymentReturnReconciliationCandidate(
        payable_identity, overpayment.identity, overpayment.version, bank_fact.bank_fact_identity,
        bank_fact.amount_ntd, remaining, status, fingerprint,
    )


def _require_offset_allowed(overpayment: GovernmentSubsidyOverpayment) -> None:
    if overpayment.status not in {
        GovernmentSubsidyOverpaymentStatus.PENDING_REVIEW,
        GovernmentSubsidyOverpaymentStatus.OFFSET_RESERVED,
    }:
        raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_disposition_conflict")


def _require_return_allowed(overpayment: GovernmentSubsidyOverpayment) -> None:
    if overpayment.status is not GovernmentSubsidyOverpaymentStatus.PENDING_REVIEW:
        raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_disposition_conflict")


def _unique_offset_intents(intents):
    if not intents:
        raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_target_invalid")
    result = {intent.claim_item_id: intent for intent in intents}
    if len(result) != len(intents):
        raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_target_ambiguous")
    return result


def _validate_offset_targets(overpayment, target_by_item, intent_by_item) -> None:
    if set(intent_by_item) - set(target_by_item):
        raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_target_invalid")
    for item_id, intent in intent_by_item.items():
        target = target_by_item[item_id]
        if target.payer_identity != overpayment.payer_identity:
            raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_cross_payer")
        if not target.submitted or not target.approved:
            raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_target_invalid")
        if intent.amount_ntd.amount > target.outstanding_amount_ntd.amount:
            raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_amount_exceeded")


def _require_within_remaining(overpayment, amount) -> None:
    if amount.amount > overpayment.remaining_amount_ntd.amount:
        raise GovernmentSubsidyOverpaymentError("government_subsidy_overpayment_amount_exceeded")


def _candidate(overpayment, amount, remaining, status, kind, payload):
    fingerprint = fingerprint_payload({
        "overpayment_identity": overpayment.identity,
        "overpayment_version": overpayment.version,
        "remaining_before_ntd": overpayment.remaining_amount_ntd.amount,
        "disposition_amount_ntd": amount.amount,
        "remaining_after_ntd": remaining.amount,
        "resulting_status": status.value,
        "disposition_kind": kind,
        "payload": _fingerprint_payload(payload),
    })
    targets = payload if kind == "offset" else ()
    return GovernmentSubsidyOverpaymentCandidate(
        overpayment.identity, overpayment.version, overpayment.remaining_amount_ntd, amount, remaining,
        status, kind, fingerprint, targets,
    )


def _fingerprint_payload(value):
    if isinstance(value, GovernmentRecipientSnapshot):
        return value.__dict__ if hasattr(value, "__dict__") else {
            field: getattr(value, field) for field in value.__dataclass_fields__
        }
    if isinstance(value, tuple) and value and isinstance(value[0], GovernmentSubsidyOffsetTarget):
        return [
            {
                "claim_item_id": item.claim_item_id,
                "claim_batch_id": item.claim_batch_id,
                "batch_version": item.batch_version,
                "outstanding_amount_ntd": item.outstanding_amount_ntd.amount,
            }
            for item in value
        ]
    return [{"claim_item_id": item.claim_item_id, "amount_ntd": item.amount_ntd.amount} for item in value]


def _sum_money(values):
    return MoneyNTD(sum(item.amount for item in values))


def _require_text(value: str, label: str) -> None:
    require_canonical_text(value, label, _IDENTITY_MAXIMUM_LENGTH)


__all__ = [
    "GovernmentRecipientSnapshot", "GovernmentOverpaymentReturnReconciliationCandidate", "GovernmentSubsidyOffsetIntent",
    "GovernmentSubsidyOffsetTarget", "GovernmentSubsidyOverpayment",
    "GovernmentSubsidyOverpaymentCandidate", "GovernmentSubsidyOverpaymentError",
    "GovernmentSubsidyOverpaymentStatus", "build_overpayment_offset_candidate",
    "GovernmentSubsidyReceiptWithOverageCandidate", "build_receipt_with_overage_candidate",
    "build_overpayment_return_candidate", "build_overpayment_return_reconciliation_candidate",
]
