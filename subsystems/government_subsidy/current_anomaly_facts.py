"""Government Subsidy-owned current facts for GOVSUB-001/002/004."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.validation import require_canonical_text, require_nonnegative_integer, require_positive_integer

GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN = "government_subsidy"
GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE = "government_subsidy_current_fact"


class GovernmentSubsidyCurrentIssueCode(StrEnum):
    RECEIPT_UNMATCHED = "GOVSUB-001"
    RECEIPT_ALLOCATION_AMBIGUOUS = "GOVSUB-002"
    REVERSAL_INVALID = "GOVSUB-004"
    RETURN_OUTGOING_OVERAGE = "GOVSUB-007"


class GovernmentSubsidyCurrentFactReason(StrEnum):
    APPROVED_BATCH_NOT_UNIQUE = "approved_batch_not_unique"
    RECEIPT_ALLOCATION_INCOMPLETE = "receipt_allocation_incomplete"
    AMOUNT_NOT_CONSERVED = "amount_not_conserved"
    ITEM_ALLOCATION_AMBIGUOUS = "item_allocation_ambiguous"
    ITEM_OUTSTANDING_EXCEEDED = "item_outstanding_exceeded"
    ALLOCATION_TOTAL_MISMATCH = "allocation_total_mismatch"
    REVERSAL_TARGET_AMBIGUOUS = "reversal_target_ambiguous"
    REVERSAL_TARGET_INVALID = "reversal_target_invalid"
    REVERSAL_AMOUNT_EXCEEDED = "reversal_amount_exceeded"
    REVERSAL_ALLOCATION_INCOMPLETE = "reversal_allocation_incomplete"
    OWNER_READBACK_INCOMPLETE = "owner_readback_incomplete"


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReceiptCurrentFact:
    bank_fact_identity: str
    owner_snapshot_token: str
    owner_version: int
    authoritative_complete: bool
    approved_batch_unique: bool
    receipt_allocation_complete: bool
    amount_conserved: bool

    def __post_init__(self) -> None:
        _validate_common(self.bank_fact_identity, self.owner_snapshot_token, self.owner_version, self.authoritative_complete)
        _validate_flags(self.approved_batch_unique, self.receipt_allocation_complete, self.amount_conserved)

    @property
    def unresolved_reason_codes(self):
        reasons = _incomplete(self.authoritative_complete)
        if not self.approved_batch_unique:
            reasons.append(GovernmentSubsidyCurrentFactReason.APPROVED_BATCH_NOT_UNIQUE)
        if not self.receipt_allocation_complete:
            reasons.append(GovernmentSubsidyCurrentFactReason.RECEIPT_ALLOCATION_INCOMPLETE)
        if not self.amount_conserved:
            reasons.append(GovernmentSubsidyCurrentFactReason.AMOUNT_NOT_CONSERVED)
        return tuple(reasons)

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyAllocationCurrentFact:
    bank_fact_identity: str
    batch_id: int
    owner_snapshot_token: str
    owner_version: int
    authoritative_complete: bool
    item_allocation_unambiguous: bool
    item_outstanding_valid: bool
    allocation_total_matches: bool

    def __post_init__(self) -> None:
        _validate_common(self.bank_fact_identity, self.owner_snapshot_token, self.owner_version, self.authoritative_complete)
        require_positive_integer(self.batch_id, "claim batch id")
        _validate_flags(self.item_allocation_unambiguous, self.item_outstanding_valid, self.allocation_total_matches)

    @property
    def unresolved_reason_codes(self):
        reasons = _incomplete(self.authoritative_complete)
        if not self.item_allocation_unambiguous:
            reasons.append(GovernmentSubsidyCurrentFactReason.ITEM_ALLOCATION_AMBIGUOUS)
        if not self.item_outstanding_valid:
            reasons.append(GovernmentSubsidyCurrentFactReason.ITEM_OUTSTANDING_EXCEEDED)
        if not self.allocation_total_matches:
            reasons.append(GovernmentSubsidyCurrentFactReason.ALLOCATION_TOTAL_MISMATCH)
        return tuple(reasons)

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReversalCurrentFact:
    reversal_bank_fact_identity: str
    source_receipt_id: int
    owner_snapshot_token: str
    owner_version: int
    authoritative_complete: bool
    reversal_target_unique: bool
    reversal_target_valid: bool
    reversal_amount_valid: bool
    reversal_allocation_complete: bool

    def __post_init__(self) -> None:
        _validate_common(self.reversal_bank_fact_identity, self.owner_snapshot_token, self.owner_version, self.authoritative_complete)
        require_positive_integer(self.source_receipt_id, "source receipt id")
        _validate_flags(self.reversal_target_unique, self.reversal_target_valid, self.reversal_amount_valid, self.reversal_allocation_complete)

    @property
    def unresolved_reason_codes(self):
        reasons = _incomplete(self.authoritative_complete)
        for valid, reason in (
            (self.reversal_target_unique, GovernmentSubsidyCurrentFactReason.REVERSAL_TARGET_AMBIGUOUS),
            (self.reversal_target_valid, GovernmentSubsidyCurrentFactReason.REVERSAL_TARGET_INVALID),
            (self.reversal_amount_valid, GovernmentSubsidyCurrentFactReason.REVERSAL_AMOUNT_EXCEEDED),
            (self.reversal_allocation_complete, GovernmentSubsidyCurrentFactReason.REVERSAL_ALLOCATION_INCOMPLETE),
        ):
            if not valid:
                reasons.append(reason)
        return tuple(reasons)

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)


GovernmentSubsidyCurrentFact = GovernmentSubsidyReceiptCurrentFact | GovernmentSubsidyAllocationCurrentFact | GovernmentSubsidyReversalCurrentFact


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyAnomalyRecheckRequest:
    definition_code: GovernmentSubsidyCurrentIssueCode
    subject_ids: tuple[str, ...]
    owner_root_ids: tuple[str, ...]
    owner_version: int
    owner_snapshot_token: str
    intent_identity: str

    def __post_init__(self) -> None:
        if not self.subject_ids or tuple(sorted(set(self.subject_ids))) != self.subject_ids:
            raise ValueError("government subsidy recheck subject ids must be sorted and unique")
        if not self.owner_root_ids or tuple(sorted(set(self.owner_root_ids))) != self.owner_root_ids:
            raise ValueError("government subsidy recheck owner roots must be sorted and unique")
        for value in (*self.subject_ids, *self.owner_root_ids):
            require_canonical_text(value, "government subsidy recheck identity", 191)
        require_nonnegative_integer(self.owner_version, "owner version")
        require_canonical_text(self.owner_snapshot_token, "owner snapshot token", 191)
        require_canonical_text(self.intent_identity, "recheck intent identity", 191)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyOverpaymentRecheckRequest:
    overpayment_identity: str
    owner_version: int
    owner_snapshot_token: str
    intent_identity: str

    def __post_init__(self) -> None:
        require_canonical_text(self.overpayment_identity, "overpayment identity", 191)
        require_nonnegative_integer(self.owner_version, "owner version")
        require_canonical_text(self.owner_snapshot_token, "owner snapshot token", 191)
        require_canonical_text(self.intent_identity, "recheck intent identity", 191)


def build_government_subsidy_recheck_requests(request, receipt, intent_identity: str) -> tuple[GovernmentSubsidyAnomalyRecheckRequest, ...]:
    bank = receipt.bank_fact_identity
    version = receipt.batch_version
    token = receipt.preview_fingerprint.value
    roots = tuple(sorted(("bank:" + bank, "batch:" + str(receipt.batch_id))))
    if receipt.kind.value == "receipt":
        return (
            GovernmentSubsidyAnomalyRecheckRequest(GovernmentSubsidyCurrentIssueCode.RECEIPT_UNMATCHED, (bank,), roots, version, token, intent_identity + ":GOVSUB-001"),
            GovernmentSubsidyAnomalyRecheckRequest(GovernmentSubsidyCurrentIssueCode.RECEIPT_ALLOCATION_AMBIGUOUS, (bank + ":" + str(receipt.batch_id),), roots, version, token, intent_identity + ":GOVSUB-002"),
        )
    source_receipt_id = getattr(request.intent, "source_receipt_id", None)
    require_positive_integer(source_receipt_id, "source receipt id")
    return (
        GovernmentSubsidyAnomalyRecheckRequest(GovernmentSubsidyCurrentIssueCode.REVERSAL_INVALID, (bank + ":" + str(source_receipt_id),), tuple(sorted((*roots, "receipt:" + str(source_receipt_id)))), version, token, intent_identity + ":GOVSUB-004"),
    )


def _validate_common(identity, token, version, complete) -> None:
    require_canonical_text(identity, "bank fact identity", 191)
    require_canonical_text(token, "owner snapshot token", 191)
    require_nonnegative_integer(version, "owner version")
    _validate_flags(complete)


def _validate_flags(*values) -> None:
    if any(type(value) is not bool for value in values):
        raise TypeError("government subsidy current-fact flags must be bool")


def _incomplete(complete: bool) -> list[GovernmentSubsidyCurrentFactReason]:
    return [] if complete else [GovernmentSubsidyCurrentFactReason.OWNER_READBACK_INCOMPLETE]


__all__ = [name for name in globals() if name.startswith("GovernmentSubsidy") or name.startswith("GOVERNMENT_SUBSIDY") or name == "build_government_subsidy_recheck_requests"]
