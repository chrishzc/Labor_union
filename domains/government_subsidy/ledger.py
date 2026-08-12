"""Pure Government Subsidy claim, receipt, allocation, and reversal rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_BANK_FACT_IDENTITY_MAXIMUM_LENGTH = 191
_CONTRACT_VERSION = "government-subsidy-ledger-v1"


class GovernmentSubsidyBatchStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"


class GovernmentSubsidyLedgerKind(StrEnum):
    RECEIPT = "receipt"
    REVERSAL = "reversal"


class GovernmentSubsidyBankDirection(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class GovernmentSubsidyErrorCode(StrEnum):
    BATCH_NOT_FOUND = "government_subsidy_batch_not_found"
    BATCH_CANDIDATE_NOT_UNIQUE = (
        "government_subsidy_batch_candidate_not_unique"
    )
    CLAIM_FACTS_INVALID = "government_subsidy_claim_facts_invalid"
    ASSIGNMENT_FACTS_STALE = "government_subsidy_assignment_facts_stale"
    APPROVAL_INVALID = "government_subsidy_approval_invalid"
    BANK_FACT_INVALID = "government_subsidy_bank_fact_invalid"
    REVIEW_REQUIRED = "government_subsidy_review_required"
    ALLOCATION_TOTAL_MISMATCH = (
        "government_subsidy_allocation_total_mismatch"
    )
    ALLOCATION_CROSS_BATCH = "government_subsidy_allocation_cross_batch"
    ALLOCATION_EXCEEDS_APPROVED = (
        "government_subsidy_allocation_exceeds_approved"
    )
    REVERSAL_TARGET_INVALID = "government_subsidy_reversal_target_invalid"
    REVERSAL_AMOUNT_EXCEEDED = (
        "government_subsidy_reversal_amount_exceeded"
    )


class GovernmentSubsidyDomainError(ValueError):
    def __init__(
        self,
        code: GovernmentSubsidyErrorCode,
        blockers: tuple[str, ...] = (),
    ) -> None:
        self.code = code
        self.blockers = blockers or (code.value,)
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class ClaimBatchIdentity:
    application_year: int
    quarter: int
    revision: int

    def __post_init__(self) -> None:
        require_positive_integer(self.application_year, "application year")
        require_positive_integer(self.revision, "claim revision")
        if self.quarter not in {1, 2, 3, 4}:
            raise ValueError("claim quarter must be between 1 and 4")

    @property
    def value(self) -> str:
        return (
            f"{self.application_year}:Q{self.quarter}:R{self.revision}"
        )


@dataclass(frozen=True, slots=True)
class OfficialAssignmentServiceFacts:
    assignment_id: int
    case_no: str
    staff_id: int
    official_service_day_count: int
    service_hours_per_day: int
    effective: bool

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        require_canonical_text(
            self.case_no,
            "case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        require_positive_integer(self.staff_id, "staff id")
        require_positive_integer(
            self.official_service_day_count,
            "official service day count",
        )
        require_positive_integer(
            self.service_hours_per_day,
            "service hours per day",
        )
        if not isinstance(self.effective, bool):
            raise TypeError("assignment effective marker must be bool")

    @property
    def official_service_hours(self) -> int:
        return self.official_service_day_count * self.service_hours_per_day


@dataclass(frozen=True, slots=True)
class ClaimItemSnapshot:
    item_id: int
    batch_id: int
    assignment_id: int
    case_no: str
    staff_id: int
    claimed_hours: int
    unit_price_ntd: MoneyNTD
    requested_amount_ntd: MoneyNTD
    approved_amount_ntd: MoneyNTD
    net_allocated_ntd: MoneyNTD

    def __post_init__(self) -> None:
        _validate_claim_item_identities(self)
        _validate_claim_item_money(self)

    @property
    def outstanding_amount_ntd(self) -> MoneyNTD:
        return self.approved_amount_ntd - self.net_allocated_ntd


@dataclass(frozen=True, slots=True)
class ClaimBatchFacts:
    batch_id: int
    identity: ClaimBatchIdentity
    aggregate_version: int
    submitted: bool
    approval_complete: bool
    items: tuple[ClaimItemSnapshot, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.batch_id, "claim batch id")
        require_nonnegative_integer(
            self.aggregate_version,
            "government subsidy version",
        )
        if not isinstance(self.identity, ClaimBatchIdentity):
            raise TypeError("claim batch identity is invalid")
        _validate_boolean(self.submitted, "submitted")
        _validate_boolean(self.approval_complete, "approval complete")
        _validate_batch_items(self)

    @property
    def requested_total_ntd(self) -> MoneyNTD:
        return _sum_money(
            item.requested_amount_ntd for item in self.items
        )

    @property
    def approved_total_ntd(self) -> MoneyNTD:
        return _sum_money(
            item.approved_amount_ntd for item in self.items
        )

    @property
    def net_allocated_total_ntd(self) -> MoneyNTD:
        return _sum_money(
            item.net_allocated_ntd for item in self.items
        )

    @property
    def outstanding_total_ntd(self) -> MoneyNTD:
        return self.approved_total_ntd - self.net_allocated_total_ntd


@dataclass(frozen=True, slots=True)
class GovernmentBankFact:
    finance_import_row_id: int
    bank_fact_identity: str
    direction: GovernmentSubsidyBankDirection
    classification_type: str
    amount_ntd: MoneyNTD
    occurred_on: date
    existing_transaction_id: int | None = None
    counterparty_account: str = ""

    # Kept cohesive so one constructor enforces the complete bank-root contract.
    def __post_init__(self) -> None:
        require_positive_integer(
            self.finance_import_row_id,
            "finance import row id",
        )
        require_canonical_text(
            self.bank_fact_identity,
            "bank fact identity",
            _BANK_FACT_IDENTITY_MAXIMUM_LENGTH,
        )
        if not isinstance(self.direction, GovernmentSubsidyBankDirection):
            raise TypeError("government subsidy bank direction is invalid")
        require_canonical_text(
            self.classification_type,
            "classification type",
            100,
        )
        if not isinstance(self.amount_ntd, MoneyNTD):
            raise TypeError("bank amount must be MoneyNTD")
        if not isinstance(self.occurred_on, date):
            raise TypeError("bank occurrence date must be a date")
        if self.existing_transaction_id is not None:
            require_positive_integer(
                self.existing_transaction_id,
                "existing transaction id",
            )
        if not isinstance(self.counterparty_account, str):
            raise TypeError("government subsidy counterparty account is invalid")


@dataclass(frozen=True, slots=True)
class AllocationIntent:
    target_identity: int
    amount_ntd: MoneyNTD

    def __post_init__(self) -> None:
        require_positive_integer(
            self.target_identity,
            "allocation target identity",
        )
        if not isinstance(self.amount_ntd, MoneyNTD):
            raise TypeError("allocation amount must be MoneyNTD")
        if self.amount_ntd.amount <= 0:
            raise ValueError("allocation amount must be positive")


@dataclass(frozen=True, slots=True)
class ReceiptIntent:
    finance_import_row_id: int
    batch_id: int | None
    allocations: tuple[AllocationIntent, ...] = ()

    def __post_init__(self) -> None:
        require_positive_integer(
            self.finance_import_row_id,
            "finance import row id",
        )
        if self.batch_id is not None:
            require_positive_integer(self.batch_id, "claim batch id")
        _validate_allocation_intents(self.allocations)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "finance_import_row_id": self.finance_import_row_id,
            "batch_id": self.batch_id,
            "allocations": _intent_payload(self.allocations),
        }


@dataclass(frozen=True, slots=True)
class SourceReceiptAllocationFacts:
    allocation_id: int
    batch_id: int
    claim_item_id: int
    receipt_amount_ntd: MoneyNTD
    reversed_amount_ntd: MoneyNTD

    def __post_init__(self) -> None:
        require_positive_integer(self.allocation_id, "allocation id")
        require_positive_integer(self.batch_id, "claim batch id")
        require_positive_integer(self.claim_item_id, "claim item id")
        _validate_source_allocation_money(self)

    @property
    def reversible_amount_ntd(self) -> MoneyNTD:
        return self.receipt_amount_ntd - self.reversed_amount_ntd


@dataclass(frozen=True, slots=True)
class SourceReceiptFacts:
    transaction_id: int
    batch_id: int
    kind: GovernmentSubsidyLedgerKind
    amount_ntd: MoneyNTD
    allocations: tuple[SourceReceiptAllocationFacts, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.transaction_id, "source transaction id")
        require_positive_integer(self.batch_id, "claim batch id")
        if not isinstance(self.kind, GovernmentSubsidyLedgerKind):
            raise TypeError("source transaction kind is invalid")
        if not isinstance(self.amount_ntd, MoneyNTD):
            raise TypeError("source receipt amount must be MoneyNTD")
        _validate_source_allocations(self)


@dataclass(frozen=True, slots=True)
class ReversalIntent:
    finance_import_row_id: int
    source_receipt_id: int
    allocations: tuple[AllocationIntent, ...] = ()

    def __post_init__(self) -> None:
        require_positive_integer(
            self.finance_import_row_id,
            "finance import row id",
        )
        require_positive_integer(
            self.source_receipt_id,
            "source receipt id",
        )
        _validate_allocation_intents(self.allocations)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "finance_import_row_id": self.finance_import_row_id,
            "source_receipt_id": self.source_receipt_id,
            "allocations": _intent_payload(self.allocations),
        }


@dataclass(frozen=True, slots=True)
class AllocationCandidate:
    claim_item_id: int
    amount_ntd: MoneyNTD
    reversal_of_allocation_id: int | None = None


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyLedgerCandidate:
    kind: GovernmentSubsidyLedgerKind
    bank_fact: GovernmentBankFact
    batch_id: int
    expected_batch_version: int
    resulting_batch_version: int
    source_receipt_id: int | None
    amount_ntd: MoneyNTD
    allocations: tuple[AllocationCandidate, ...]
    requested_total_ntd: MoneyNTD
    approved_total_ntd: MoneyNTD
    before_net_allocated_ntd: MoneyNTD
    after_net_allocated_ntd: MoneyNTD
    outstanding_ntd: MoneyNTD
    before_status: GovernmentSubsidyBatchStatus
    after_status: GovernmentSubsidyBatchStatus
    fingerprint: PreviewFingerprint


# Kept cohesive so the immutable claim snapshot is assembled in one place.
def build_claim_item_snapshot(
    item_id: int,
    batch_id: int,
    service_facts: OfficialAssignmentServiceFacts,
    unit_price_ntd: MoneyNTD,
    approved_amount_ntd: MoneyNTD | None = None,
    net_allocated_ntd: MoneyNTD | None = None,
) -> ClaimItemSnapshot:
    _require_effective_assignment(service_facts)
    requested = unit_price_ntd * service_facts.official_service_hours
    return ClaimItemSnapshot(
        item_id,
        batch_id,
        service_facts.assignment_id,
        service_facts.case_no,
        service_facts.staff_id,
        service_facts.official_service_hours,
        unit_price_ntd,
        requested,
        approved_amount_ntd or MoneyNTD(0),
        net_allocated_ntd or MoneyNTD(0),
    )


def validate_approval_amounts(
    items: tuple[ClaimItemSnapshot, ...],
    approval_amounts: tuple[AllocationIntent, ...],
) -> MoneyNTD:
    _validate_allocation_intents(approval_amounts)
    approvals = _unique_intent_map(
        approval_amounts,
        GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID,
    )
    if set(approvals) != {item.item_id for item in items}:
        _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)
    for item in items:
        if approvals[item.item_id].amount > item.requested_amount_ntd.amount:
            _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)
    return _sum_money(approvals.values())


def build_receipt_candidate(
    bank_fact: GovernmentBankFact,
    batches: tuple[ClaimBatchFacts, ...],
    intent: ReceiptIntent,
) -> GovernmentSubsidyLedgerCandidate:
    _validate_bank_fact(bank_fact, GovernmentSubsidyBankDirection.INCOMING)
    _validate_bank_identity(intent.finance_import_row_id, bank_fact)
    batch = _select_receipt_batch(bank_fact, batches, intent.batch_id)
    allocations = _receipt_allocations(bank_fact, batch, intent.allocations)
    after_net = batch.net_allocated_total_ntd + bank_fact.amount_ntd
    return _ledger_candidate(
        GovernmentSubsidyLedgerKind.RECEIPT,
        bank_fact,
        batch,
        None,
        allocations,
        after_net,
    )


# Kept cohesive so reversal validation and its resulting projection stay atomic.
def build_reversal_candidate(
    bank_fact: GovernmentBankFact,
    batch: ClaimBatchFacts,
    source_receipt: SourceReceiptFacts,
    intent: ReversalIntent,
) -> GovernmentSubsidyLedgerCandidate:
    _validate_bank_fact(bank_fact, GovernmentSubsidyBankDirection.OUTGOING)
    _validate_bank_identity(intent.finance_import_row_id, bank_fact)
    _validate_source_receipt(batch, source_receipt, intent)
    allocations = _reversal_allocations(
        bank_fact,
        source_receipt,
        intent.allocations,
    )
    after_net = batch.net_allocated_total_ntd - bank_fact.amount_ntd
    if after_net.amount < 0:
        _raise(GovernmentSubsidyErrorCode.REVERSAL_AMOUNT_EXCEEDED)
    return _ledger_candidate(
        GovernmentSubsidyLedgerKind.REVERSAL,
        bank_fact,
        batch,
        source_receipt.transaction_id,
        allocations,
        after_net,
    )


def reduce_batch_status(
    batch: ClaimBatchFacts,
    net_allocated_ntd: MoneyNTD | None = None,
) -> GovernmentSubsidyBatchStatus:
    net = net_allocated_ntd or batch.net_allocated_total_ntd
    if not batch.submitted:
        return GovernmentSubsidyBatchStatus.DRAFT
    if not batch.approval_complete:
        return GovernmentSubsidyBatchStatus.SUBMITTED
    if net.is_zero:
        return GovernmentSubsidyBatchStatus.APPROVED
    if net == batch.approved_total_ntd:
        return GovernmentSubsidyBatchStatus.PAID
    return GovernmentSubsidyBatchStatus.PARTIALLY_PAID


def _select_receipt_batch(bank_fact, batches, explicit_batch_id):
    eligible = tuple(
        batch
        for batch in batches
        if _batch_can_receive(batch, bank_fact.amount_ntd)
    )
    if explicit_batch_id is not None:
        eligible = tuple(
            batch for batch in eligible if batch.batch_id == explicit_batch_id
        )
    if len(eligible) != 1:
        _raise(GovernmentSubsidyErrorCode.REVIEW_REQUIRED)
    return eligible[0]


def _batch_can_receive(batch, amount):
    return (
        batch.submitted
        and batch.approval_complete
        and batch.approved_total_ntd.amount > 0
        and amount.amount <= batch.outstanding_total_ntd.amount
    )


# Kept cohesive because these branches define the complete auto-allocation rule.
def _receipt_allocations(bank_fact, batch, intents):
    if intents:
        return _manual_receipt_allocations(bank_fact, batch, intents)
    outstanding = tuple(
        item for item in batch.items if item.outstanding_amount_ntd.amount > 0
    )
    if bank_fact.amount_ntd == batch.outstanding_total_ntd:
        return tuple(
            AllocationCandidate(
                item.item_id,
                item.outstanding_amount_ntd,
            )
            for item in outstanding
        )
    if len(outstanding) == 1:
        return (
            AllocationCandidate(
                outstanding[0].item_id,
                bank_fact.amount_ntd,
            ),
        )
    _raise(GovernmentSubsidyErrorCode.REVIEW_REQUIRED)


def _manual_receipt_allocations(bank_fact, batch, intents):
    intent_map = _unique_intent_map(
        intents,
        GovernmentSubsidyErrorCode.ALLOCATION_TOTAL_MISMATCH,
    )
    item_map = {item.item_id: item for item in batch.items}
    if not set(intent_map).issubset(item_map):
        _raise(GovernmentSubsidyErrorCode.ALLOCATION_CROSS_BATCH)
    if _sum_money(intent_map.values()) != bank_fact.amount_ntd:
        _raise(GovernmentSubsidyErrorCode.ALLOCATION_TOTAL_MISMATCH)
    _validate_receipt_capacities(intent_map, item_map)
    return tuple(
        AllocationCandidate(item_id, amount)
        for item_id, amount in sorted(intent_map.items())
    )


def _validate_receipt_capacities(intent_map, item_map):
    for item_id, amount in intent_map.items():
        if amount.amount > item_map[item_id].outstanding_amount_ntd.amount:
            _raise(
                GovernmentSubsidyErrorCode.ALLOCATION_EXCEEDS_APPROVED
            )


def _validate_source_receipt(batch, source, intent):
    if source.kind is not GovernmentSubsidyLedgerKind.RECEIPT:
        _raise(GovernmentSubsidyErrorCode.REVERSAL_TARGET_INVALID)
    if source.transaction_id != intent.source_receipt_id:
        _raise(GovernmentSubsidyErrorCode.REVERSAL_TARGET_INVALID)
    if source.batch_id != batch.batch_id:
        _raise(GovernmentSubsidyErrorCode.ALLOCATION_CROSS_BATCH)


# Kept cohesive because these branches define the complete reversal split rule.
def _reversal_allocations(bank_fact, source, intents):
    if intents:
        return _manual_reversal_allocations(bank_fact, source, intents)
    reversible = tuple(
        item for item in source.allocations
        if item.reversible_amount_ntd.amount > 0
    )
    total = _sum_money(item.reversible_amount_ntd for item in reversible)
    if bank_fact.amount_ntd == total:
        return tuple(_reversal_candidate(item) for item in reversible)
    if len(reversible) == 1:
        item = reversible[0]
        _validate_reversal_capacity(bank_fact.amount_ntd, item)
        return (
            AllocationCandidate(
                item.claim_item_id,
                bank_fact.amount_ntd,
                item.allocation_id,
            ),
        )
    _raise(GovernmentSubsidyErrorCode.REVIEW_REQUIRED)


def _manual_reversal_allocations(bank_fact, source, intents):
    intent_map = _unique_intent_map(
        intents,
        GovernmentSubsidyErrorCode.ALLOCATION_TOTAL_MISMATCH,
    )
    source_map = {
        allocation.allocation_id: allocation
        for allocation in source.allocations
    }
    if not set(intent_map).issubset(source_map):
        _raise(GovernmentSubsidyErrorCode.REVERSAL_TARGET_INVALID)
    if _sum_money(intent_map.values()) != bank_fact.amount_ntd:
        _raise(GovernmentSubsidyErrorCode.ALLOCATION_TOTAL_MISMATCH)
    return tuple(
        _manual_reversal_candidate(
            source_map[allocation_id],
            amount,
        )
        for allocation_id, amount in sorted(intent_map.items())
    )


def _manual_reversal_candidate(source, amount):
    _validate_reversal_capacity(amount, source)
    return AllocationCandidate(
        source.claim_item_id,
        amount,
        source.allocation_id,
    )


def _reversal_candidate(source):
    return AllocationCandidate(
        source.claim_item_id,
        source.reversible_amount_ntd,
        source.allocation_id,
    )


def _validate_reversal_capacity(amount, source):
    if amount.amount > source.reversible_amount_ntd.amount:
        _raise(GovernmentSubsidyErrorCode.REVERSAL_AMOUNT_EXCEEDED)


# Kept cohesive so every candidate field and fingerprint share one source map.
def _ledger_candidate(kind, bank_fact, batch, source_id, allocations, after_net):
    _validate_net_range(batch, after_net)
    before_status = reduce_batch_status(batch)
    after_status = reduce_batch_status(batch, after_net)
    payload = _candidate_payload(
        kind,
        bank_fact,
        batch,
        source_id,
        allocations,
        after_net,
        after_status,
    )
    return GovernmentSubsidyLedgerCandidate(
        kind,
        bank_fact,
        batch.batch_id,
        batch.aggregate_version,
        batch.aggregate_version + 1,
        source_id,
        bank_fact.amount_ntd,
        allocations,
        batch.requested_total_ntd,
        batch.approved_total_ntd,
        batch.net_allocated_total_ntd,
        after_net,
        batch.approved_total_ntd - after_net,
        before_status,
        after_status,
        fingerprint_payload(payload),
    )


def _candidate_payload(
    kind,
    bank_fact,
    batch,
    source_id,
    allocations,
    after_net,
    after_status,
):
    return {
        "contract_version": _CONTRACT_VERSION,
        "kind": kind.value,
        "bank_fact": _bank_payload(bank_fact),
        "batch": _batch_payload(batch),
        "source_receipt_id": source_id,
        "allocations": _candidate_allocations_payload(allocations),
        "after_net_allocated_ntd": after_net.amount,
        "after_status": after_status.value,
    }


def _bank_payload(bank_fact):
    return {
        "finance_import_row_id": bank_fact.finance_import_row_id,
        "bank_fact_identity": bank_fact.bank_fact_identity,
        "direction": bank_fact.direction.value,
        "classification_type": bank_fact.classification_type,
        "amount_ntd": bank_fact.amount_ntd.amount,
        "occurred_on": bank_fact.occurred_on.isoformat(),
        "existing_transaction_id": bank_fact.existing_transaction_id,
    }


def _batch_payload(batch):
    return {
        "batch_id": batch.batch_id,
        "identity": batch.identity.value,
        "aggregate_version": batch.aggregate_version,
        "submitted": batch.submitted,
        "approval_complete": batch.approval_complete,
        "items": tuple(_claim_item_payload(item) for item in batch.items),
    }


def _claim_item_payload(item):
    return {
        "item_id": item.item_id,
        "assignment_id": item.assignment_id,
        "case_no": item.case_no,
        "staff_id": item.staff_id,
        "claimed_hours": item.claimed_hours,
        "unit_price_ntd": item.unit_price_ntd.amount,
        "requested_amount_ntd": item.requested_amount_ntd.amount,
        "approved_amount_ntd": item.approved_amount_ntd.amount,
        "net_allocated_ntd": item.net_allocated_ntd.amount,
    }


def _candidate_allocations_payload(allocations):
    return tuple(
        {
            "claim_item_id": allocation.claim_item_id,
            "amount_ntd": allocation.amount_ntd.amount,
            "reversal_of_allocation_id": (
                allocation.reversal_of_allocation_id
            ),
        }
        for allocation in allocations
    )


def _validate_bank_fact(bank_fact, expected_direction):
    if bank_fact.direction is not expected_direction:
        _raise(GovernmentSubsidyErrorCode.BANK_FACT_INVALID)
    if bank_fact.classification_type != "government_subsidy":
        _raise(GovernmentSubsidyErrorCode.BANK_FACT_INVALID)
    if bank_fact.amount_ntd.amount <= 0:
        _raise(GovernmentSubsidyErrorCode.BANK_FACT_INVALID)
    if bank_fact.existing_transaction_id is not None:
        _raise(GovernmentSubsidyErrorCode.BANK_FACT_INVALID)


def _validate_bank_identity(finance_import_row_id, bank_fact):
    if finance_import_row_id != bank_fact.finance_import_row_id:
        _raise(GovernmentSubsidyErrorCode.BANK_FACT_INVALID)


def _validate_net_range(batch, after_net):
    if after_net.amount < 0:
        _raise(GovernmentSubsidyErrorCode.REVERSAL_AMOUNT_EXCEEDED)
    if after_net.amount > batch.approved_total_ntd.amount:
        _raise(GovernmentSubsidyErrorCode.ALLOCATION_EXCEEDS_APPROVED)


def _validate_claim_item_identities(item):
    require_positive_integer(item.item_id, "claim item id")
    require_positive_integer(item.batch_id, "claim batch id")
    require_positive_integer(item.assignment_id, "assignment id")
    require_canonical_text(
        item.case_no,
        "case number",
        _CASE_NUMBER_MAXIMUM_LENGTH,
    )
    require_positive_integer(item.staff_id, "staff id")
    require_positive_integer(item.claimed_hours, "claimed hours")


def _validate_claim_item_money(item):
    money_values = (
        item.unit_price_ntd,
        item.requested_amount_ntd,
        item.approved_amount_ntd,
        item.net_allocated_ntd,
    )
    if any(not isinstance(value, MoneyNTD) for value in money_values):
        raise TypeError("claim item money must be MoneyNTD")
    expected = item.unit_price_ntd.amount * item.claimed_hours
    if item.requested_amount_ntd.amount != expected:
        _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)
    if not 0 <= item.approved_amount_ntd.amount <= expected:
        _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)
    if not 0 <= item.net_allocated_ntd.amount <= item.approved_amount_ntd.amount:
        _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)


def _validate_batch_items(batch):
    if not isinstance(batch.items, tuple) or not batch.items:
        _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)
    if any(not isinstance(item, ClaimItemSnapshot) for item in batch.items):
        raise TypeError("claim batch contains invalid items")
    if any(item.batch_id != batch.batch_id for item in batch.items):
        _raise(GovernmentSubsidyErrorCode.ALLOCATION_CROSS_BATCH)
    item_ids = tuple(item.item_id for item in batch.items)
    if item_ids != tuple(sorted(set(item_ids))):
        _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)


def _validate_source_allocation_money(allocation):
    values = (
        allocation.receipt_amount_ntd,
        allocation.reversed_amount_ntd,
    )
    if any(not isinstance(value, MoneyNTD) for value in values):
        raise TypeError("source allocation money must be MoneyNTD")
    if allocation.receipt_amount_ntd.amount <= 0:
        _raise(GovernmentSubsidyErrorCode.REVERSAL_TARGET_INVALID)
    reversed_amount = allocation.reversed_amount_ntd.amount
    receipt_amount = allocation.receipt_amount_ntd.amount
    if not 0 <= reversed_amount <= receipt_amount:
        _raise(GovernmentSubsidyErrorCode.REVERSAL_AMOUNT_EXCEEDED)


def _validate_source_allocations(source):
    if not isinstance(source.allocations, tuple) or not source.allocations:
        _raise(GovernmentSubsidyErrorCode.REVERSAL_TARGET_INVALID)
    if any(
        allocation.batch_id != source.batch_id
        for allocation in source.allocations
    ):
        _raise(GovernmentSubsidyErrorCode.ALLOCATION_CROSS_BATCH)
    allocated = _sum_money(
        allocation.receipt_amount_ntd for allocation in source.allocations
    )
    if allocated != source.amount_ntd:
        _raise(GovernmentSubsidyErrorCode.ALLOCATION_TOTAL_MISMATCH)


def _validate_allocation_intents(intents):
    if not isinstance(intents, tuple):
        raise TypeError("allocation intents must be a tuple")
    if any(not isinstance(intent, AllocationIntent) for intent in intents):
        raise TypeError("allocation intents contain an invalid value")


def _unique_intent_map(intents, duplicate_error):
    result: dict[int, MoneyNTD] = {}
    for intent in intents:
        if intent.target_identity in result:
            _raise(duplicate_error)
        result[intent.target_identity] = intent.amount_ntd
    return result


def _intent_payload(intents):
    return tuple(
        {
            "target_identity": intent.target_identity,
            "amount_ntd": intent.amount_ntd.amount,
        }
        for intent in intents
    )


def _require_effective_assignment(facts):
    if not facts.effective:
        _raise(GovernmentSubsidyErrorCode.ASSIGNMENT_FACTS_STALE)


def _sum_money(values) -> MoneyNTD:
    return MoneyNTD(sum(value.amount for value in values))


def _validate_boolean(value, field_name):
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool")


def _raise(code):
    raise GovernmentSubsidyDomainError(code)


__all__ = [
    "AllocationCandidate",
    "AllocationIntent",
    "ClaimBatchFacts",
    "ClaimBatchIdentity",
    "ClaimItemSnapshot",
    "GovernmentBankFact",
    "GovernmentSubsidyBankDirection",
    "GovernmentSubsidyBatchStatus",
    "GovernmentSubsidyDomainError",
    "GovernmentSubsidyErrorCode",
    "GovernmentSubsidyLedgerCandidate",
    "GovernmentSubsidyLedgerKind",
    "OfficialAssignmentServiceFacts",
    "ReceiptIntent",
    "ReversalIntent",
    "SourceReceiptAllocationFacts",
    "SourceReceiptFacts",
    "build_claim_item_snapshot",
    "build_receipt_candidate",
    "build_reversal_candidate",
    "reduce_batch_status",
    "validate_approval_amounts",
]
