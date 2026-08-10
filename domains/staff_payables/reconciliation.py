"""Pure Staff Payables status reduction and exact payout reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text, require_positive_integer

_IDENTITY_MAXIMUM_LENGTH = 191


class StaffPayableStatus(StrEnum):
    PAYABLE = "payable"
    COMPLETED = "completed"
    ANOMALY = "anomaly"


class StaffPayoutEventType(StrEnum):
    PAYOUT = "payout"
    RETURN = "return"
    REVERSAL = "reversal"


class BankTransactionDirection(StrEnum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"


class StaffPayoutEventStatus(StrEnum):
    SUCCEEDED = "succeeded"


@dataclass(frozen=True, slots=True)
class StaffPayoutEvent:
    identity: str
    event_type: StaffPayoutEventType
    amount: MoneyNTD
    reversal_of_event_identity: str | None = None
    status: StaffPayoutEventStatus = StaffPayoutEventStatus.SUCCEEDED

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "payout event identity")
        _require_event_type(self.event_type)
        _require_positive_money(self.amount, "payout event amount")
        _validate_optional_identity(
            self.reversal_of_event_identity,
            "reversal source event identity",
        )
        if self.status is not StaffPayoutEventStatus.SUCCEEDED:
            raise ValueError("formal staff payout events must be succeeded")


@dataclass(frozen=True, slots=True)
class StaffPayableFacts:
    obligation_identity: str
    staff_id: int
    amount_due: MoneyNTD
    events: tuple[StaffPayoutEvent, ...] = ()

    def __post_init__(self) -> None:
        _validate_identity(self.obligation_identity, "obligation identity")
        require_positive_integer(self.staff_id, "staff id")
        _require_positive_money(self.amount_due, "staff obligation amount")
        if not isinstance(self.events, tuple):
            raise TypeError("payout events must be a tuple")
        identities = tuple(event.identity for event in self.events)
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate staff payout event identity")


@dataclass(frozen=True, slots=True)
class StaffPayableProjection:
    obligation_identity: str
    staff_id: int
    obligation_amount: MoneyNTD
    net_paid: MoneyNTD
    balance: MoneyNTD
    status: StaffPayableStatus


@dataclass(frozen=True, slots=True)
class OutgoingBankFact:
    identity: str
    staff_id: int
    amount: MoneyNTD
    bank_account_identity: str | None = None
    direction: BankTransactionDirection = BankTransactionDirection.OUTGOING
    raw_fact_identity: str | None = None
    eligible: bool = True
    blocking_anomalies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "outgoing bank fact identity")
        require_positive_integer(self.staff_id, "staff id")
        _require_positive_money(self.amount, "outgoing bank amount")
        _validate_optional_identity(
            self.bank_account_identity,
            "bank account identity",
        )
        _validate_optional_identity(self.raw_fact_identity, "raw bank fact identity")
        if not isinstance(self.direction, BankTransactionDirection):
            raise TypeError("bank transaction direction is invalid")
        if not isinstance(self.eligible, bool):
            raise TypeError("bank fact eligibility must be bool")
        _validate_blockers(self.blocking_anomalies)

    @property
    def canonical_raw_fact_identity(self) -> str:
        return self.raw_fact_identity or self.identity


@dataclass(frozen=True, slots=True)
class StaffPrimaryBankAccount:
    identity: str
    owner_staff_id: int
    active: bool = True
    primary: bool = True

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "staff bank account identity")
        require_positive_integer(self.owner_staff_id, "bank account owner staff id")
        if not isinstance(self.active, bool) or not isinstance(self.primary, bool):
            raise TypeError("bank account flags must be bool")


@dataclass(frozen=True, slots=True)
class StaffPayoutAllocation:
    bank_fact_identity: str
    obligation_identity: str
    amount: MoneyNTD

    def __post_init__(self) -> None:
        _validate_identity(self.bank_fact_identity, "bank fact identity")
        _validate_identity(self.obligation_identity, "obligation identity")
        _require_positive_money(self.amount, "payout allocation amount")


@dataclass(frozen=True, slots=True)
class StaffPayoutLedgerEventCandidate:
    identity: str
    event_type: StaffPayoutEventType
    status: StaffPayoutEventStatus
    staff_id: int
    amount: MoneyNTD
    finance_import_fact_identity: str | None = None
    reversal_of_event_identity: str | None = None

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "payout event candidate identity")
        _require_event_type(self.event_type)
        require_positive_integer(self.staff_id, "payout event staff id")
        _require_positive_money(self.amount, "payout event candidate amount")
        _validate_optional_identity(
            self.finance_import_fact_identity,
            "finance import fact identity",
        )
        _validate_optional_identity(
            self.reversal_of_event_identity,
            "reversal source event identity",
        )
        if self.status is not StaffPayoutEventStatus.SUCCEEDED:
            raise ValueError("formal staff payout events must be succeeded")


@dataclass(frozen=True, slots=True)
class StaffPayoutObligationLinkCandidate:
    event_identity: str
    obligation_identity: str
    allocated_amount: MoneyNTD

    def __post_init__(self) -> None:
        _validate_identity(self.event_identity, "payout event identity")
        _validate_identity(self.obligation_identity, "obligation identity")
        _require_positive_money(self.allocated_amount, "link allocation amount")


@dataclass(frozen=True, slots=True)
class StaffPayoutCandidate:
    staff_id: int
    bank_total: MoneyNTD
    obligation_total: MoneyNTD
    allocations: tuple[StaffPayoutAllocation, ...]
    fingerprint: PreviewFingerprint
    events: tuple[StaffPayoutLedgerEventCandidate, ...] = ()
    obligation_links: tuple[StaffPayoutObligationLinkCandidate, ...] = ()
    resulting_status: StaffPayableStatus = StaffPayableStatus.COMPLETED


@dataclass(frozen=True, slots=True)
class StaffPayoutReopenFact:
    identity: str
    event_type: StaffPayoutEventType
    staff_id: int
    amount: MoneyNTD
    source_payout_event_identity: str
    succeeded: bool = True
    blocking_anomalies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_identity(self.identity, "payout reopen fact identity")
        _require_event_type(self.event_type)
        _validate_identity(
            self.source_payout_event_identity,
            "source payout event identity",
        )
        require_positive_integer(self.staff_id, "payout reopen staff id")
        _require_positive_money(self.amount, "payout reopen amount")
        if self.event_type is StaffPayoutEventType.PAYOUT:
            raise ValueError("staff_payout_reversal_invalid")
        if not isinstance(self.succeeded, bool):
            raise TypeError("payout reopen success flag must be bool")
        _validate_blockers(self.blocking_anomalies)


@dataclass(frozen=True, slots=True)
class StaffPayoutReopenCandidate:
    staff_id: int
    event: StaffPayoutLedgerEventCandidate
    obligation_links: tuple[StaffPayoutObligationLinkCandidate, ...]
    resulting_status: StaffPayableStatus
    fingerprint: PreviewFingerprint


def project_staff_payable(facts: StaffPayableFacts) -> StaffPayableProjection:
    net_paid = MoneyNTD(sum(_signed_amount(event) for event in facts.events))
    balance = facts.amount_due - net_paid
    return StaffPayableProjection(
        obligation_identity=facts.obligation_identity,
        staff_id=facts.staff_id,
        obligation_amount=facts.amount_due,
        net_paid=net_paid,
        balance=balance,
        status=_payable_status(facts.amount_due, net_paid),
    )


def build_staff_payout_candidate(
    bank_facts: tuple[OutgoingBankFact, ...],
    payable_facts: tuple[StaffPayableFacts, ...],
    *,
    bank_accounts: tuple[StaffPrimaryBankAccount, ...] = (),
    blocking_anomalies: tuple[str, ...] = (),
    require_primary_account_owner: bool = False,
) -> StaffPayoutCandidate:
    staff_id = _validate_payout_inputs(
        bank_facts,
        payable_facts,
        blocking_anomalies,
    )
    return _build_owned_payout(
        staff_id,
        bank_facts,
        payable_facts,
        bank_accounts,
        require_primary_account_owner,
    )


def _build_owned_payout(
    staff_id,
    bank_facts,
    payable_facts,
    bank_accounts,
    require_primary_account_owner,
):
    _validate_primary_account_owners(
        bank_facts,
        bank_accounts,
        staff_id,
        require_primary_account_owner,
    )
    ordered_banks = tuple(sorted(bank_facts, key=lambda item: item.identity))
    ordered_payables = tuple(
        sorted(payable_facts, key=lambda item: item.obligation_identity)
    )
    return _build_exact_payout(staff_id, ordered_banks, ordered_payables)


def build_staff_payout_reopen_candidate(
    reopen_fact: StaffPayoutReopenFact,
    payable_facts: tuple[StaffPayableFacts, ...],
) -> StaffPayoutReopenCandidate:
    ordered_payables = _validate_reopen_inputs(reopen_fact, payable_facts)
    links = tuple(
        _reopen_link(reopen_fact, payable) for payable in ordered_payables
    )
    _validate_reopen_total(reopen_fact, links)
    return _reopen_candidate(reopen_fact, links)


def _build_exact_payout(staff_id, ordered_banks, ordered_payables):
    bank_total = MoneyNTD(sum(item.amount.amount for item in ordered_banks))
    obligation_total = MoneyNTD(
        sum(item.amount_due.amount for item in ordered_payables)
    )
    if bank_total != obligation_total:
        raise ValueError("staff_payout_amount_mismatch")
    allocations = _allocate(ordered_banks, ordered_payables)
    _validate_exact_allocation(ordered_banks, ordered_payables, allocations)
    return _payout_candidate(
        staff_id,
        bank_total,
        obligation_total,
        allocations,
        ordered_banks,
    )


def _payout_candidate(
    staff_id,
    bank_total,
    obligation_total,
    allocations,
    ordered_banks,
):
    events = tuple(_payout_event(bank_fact) for bank_fact in ordered_banks)
    links = _payout_links(events, allocations)
    return StaffPayoutCandidate(
        staff_id,
        bank_total,
        obligation_total,
        allocations,
        fingerprint_payload(_candidate_payload(staff_id, allocations, events)),
        events,
        links,
    )


def _validate_payout_inputs(
    bank_facts,
    payable_facts,
    blocking_anomalies,
) -> int:
    if not bank_facts or not payable_facts:
        raise ValueError("invalid_staff_payout_intent")
    _raise_if_bank_facts_ineligible(bank_facts, blocking_anomalies)
    staff_ids = {
        *(item.staff_id for item in bank_facts),
        *(item.staff_id for item in payable_facts),
    }
    if len(staff_ids) != 1:
        raise ValueError("cross_staff_allocation_forbidden")
    _validate_payable_statuses(payable_facts)
    return next(iter(staff_ids))


def _validate_payable_statuses(payable_facts) -> None:
    if any(
        project_staff_payable(item).status is not StaffPayableStatus.PAYABLE
        for item in payable_facts
    ):
        raise ValueError("staff_obligation_not_exactly_settled")


def _raise_if_bank_facts_ineligible(bank_facts, blocking_anomalies) -> None:
    _validate_blockers(blocking_anomalies)
    raw_identities = tuple(item.canonical_raw_fact_identity for item in bank_facts)
    has_duplicate_raw_fact = len(raw_identities) != len(set(raw_identities))
    has_ineligible_fact = any(_bank_fact_is_ineligible(item) for item in bank_facts)
    if blocking_anomalies or has_duplicate_raw_fact or has_ineligible_fact:
        raise ValueError("outgoing_bank_fact_not_eligible")


def _bank_fact_is_ineligible(bank_fact) -> bool:
    return (
        not bank_fact.eligible
        or bank_fact.direction is not BankTransactionDirection.OUTGOING
        or bool(bank_fact.blocking_anomalies)
    )


def _validate_primary_account_owners(
    bank_facts,
    bank_accounts,
    staff_id,
    required,
) -> None:
    if not required and not bank_accounts:
        return
    for bank_fact in bank_facts:
        _validate_bank_fact_owner(bank_fact, bank_accounts, staff_id)


def _validate_bank_fact_owner(bank_fact, bank_accounts, staff_id) -> None:
    if bank_fact.bank_account_identity is None:
        raise ValueError("staff_bank_account_ambiguous")
    owners = tuple(
        account.owner_staff_id
        for account in bank_accounts
        if _is_matching_primary_account(account, bank_fact.bank_account_identity)
    )
    if len(owners) != 1:
        raise ValueError("staff_bank_account_ambiguous")
    if owners[0] != staff_id:
        raise ValueError("cross_staff_allocation_forbidden")


def _is_matching_primary_account(account, account_identity) -> bool:
    return (
        account.identity == account_identity
        and account.active
        and account.primary
    )


def _allocate(bank_facts, payable_facts) -> tuple[StaffPayoutAllocation, ...]:
    allocations: list[StaffPayoutAllocation] = []
    remaining_banks = [[item, item.amount.amount] for item in bank_facts]
    remaining_payables = [[item, item.amount_due.amount] for item in payable_facts]
    while remaining_banks:
        allocation, amount = _next_allocation(remaining_banks, remaining_payables)
        allocations.append(allocation)
        _consume_front(remaining_banks, amount)
        _consume_front(remaining_payables, amount)
    return tuple(allocations)


def _next_allocation(remaining_banks, remaining_payables):
    bank_fact, bank_amount = remaining_banks[0]
    payable, payable_amount = remaining_payables[0]
    amount = min(bank_amount, payable_amount)
    allocation = StaffPayoutAllocation(
        bank_fact.identity,
        payable.obligation_identity,
        MoneyNTD(amount),
    )
    return allocation, amount


def _consume_front(remaining_values, consumed_amount) -> None:
    remaining_values[0][1] -= consumed_amount
    if remaining_values[0][1] == 0:
        remaining_values.pop(0)


def _validate_exact_allocation(bank_facts, payable_facts, allocations) -> None:
    bank_totals = _allocation_totals(
        allocations,
        lambda item: item.bank_fact_identity,
    )
    payable_totals = _allocation_totals(
        allocations,
        lambda item: item.obligation_identity,
    )
    if any(bank_totals[item.identity] != item.amount for item in bank_facts):
        raise ValueError("staff_obligation_not_exactly_settled")
    if any(
        payable_totals[item.obligation_identity] != item.amount_due
        for item in payable_facts
    ):
        raise ValueError("staff_obligation_not_exactly_settled")


def _allocation_totals(
    allocations,
    identity_getter: Callable[[StaffPayoutAllocation], str],
) -> dict[str, MoneyNTD]:
    totals: dict[str, MoneyNTD] = {}
    for allocation in allocations:
        identity = identity_getter(allocation)
        totals[identity] = totals.get(identity, MoneyNTD(0)) + allocation.amount
    return totals


def _payable_status(amount_due: MoneyNTD, net_paid: MoneyNTD):
    if net_paid.amount == 0:
        return StaffPayableStatus.PAYABLE
    if net_paid == amount_due:
        return StaffPayableStatus.COMPLETED
    return StaffPayableStatus.ANOMALY


def _signed_amount(event: StaffPayoutEvent) -> int:
    if event.event_type is StaffPayoutEventType.PAYOUT:
        return event.amount.amount
    return -event.amount.amount


def _payout_event(bank_fact) -> StaffPayoutLedgerEventCandidate:
    return StaffPayoutLedgerEventCandidate(
        identity=_derived_event_identity(
            StaffPayoutEventType.PAYOUT,
            bank_fact.identity,
        ),
        event_type=StaffPayoutEventType.PAYOUT,
        status=StaffPayoutEventStatus.SUCCEEDED,
        staff_id=bank_fact.staff_id,
        amount=bank_fact.amount,
        finance_import_fact_identity=bank_fact.identity,
    )


def _payout_links(events, allocations):
    event_by_bank = {
        event.finance_import_fact_identity: event.identity for event in events
    }
    return tuple(
        StaffPayoutObligationLinkCandidate(
            event_by_bank[item.bank_fact_identity],
            item.obligation_identity,
            item.amount,
        )
        for item in allocations
    )


def _validate_reopen_inputs(reopen_fact, payable_facts):
    if not reopen_fact.succeeded or reopen_fact.blocking_anomalies:
        raise ValueError("staff_payout_reversal_invalid")
    if not payable_facts:
        raise ValueError("staff_payable_not_found")
    if any(item.staff_id != reopen_fact.staff_id for item in payable_facts):
        raise ValueError("cross_staff_allocation_forbidden")
    ordered = tuple(
        sorted(payable_facts, key=lambda item: item.obligation_identity)
    )
    for payable in ordered:
        _validate_reopen_payable(reopen_fact, payable)
    return ordered


def _validate_reopen_payable(reopen_fact, payable) -> None:
    if project_staff_payable(payable).status is not StaffPayableStatus.COMPLETED:
        raise ValueError("staff_payout_reversal_invalid")
    source_events = tuple(
        event
        for event in payable.events
        if event.identity == reopen_fact.source_payout_event_identity
        and event.event_type is StaffPayoutEventType.PAYOUT
    )
    if len(source_events) != 1 or source_events[0].amount != payable.amount_due:
        raise ValueError("staff_payout_reversal_invalid")
    if any(
        event.reversal_of_event_identity
        == reopen_fact.source_payout_event_identity
        for event in payable.events
    ):
        raise ValueError("staff_payout_reversal_invalid")


def _reopen_link(reopen_fact, payable) -> StaffPayoutObligationLinkCandidate:
    source_amount = next(
        event.amount
        for event in payable.events
        if event.identity == reopen_fact.source_payout_event_identity
    )
    return StaffPayoutObligationLinkCandidate(
        reopen_fact.identity,
        payable.obligation_identity,
        source_amount,
    )


def _validate_reopen_total(reopen_fact, links) -> None:
    allocated_total = MoneyNTD(
        sum(item.allocated_amount.amount for item in links)
    )
    if allocated_total != reopen_fact.amount:
        raise ValueError("staff_payout_reversal_invalid")


def _reopen_candidate(reopen_fact, links) -> StaffPayoutReopenCandidate:
    event = StaffPayoutLedgerEventCandidate(
        reopen_fact.identity,
        reopen_fact.event_type,
        StaffPayoutEventStatus.SUCCEEDED,
        reopen_fact.staff_id,
        reopen_fact.amount,
        reversal_of_event_identity=reopen_fact.source_payout_event_identity,
    )
    return StaffPayoutReopenCandidate(
        reopen_fact.staff_id,
        event,
        links,
        StaffPayableStatus.PAYABLE,
        fingerprint_payload(_reopen_payload(event, links)),
    )


def _candidate_payload(staff_id, allocations, events) -> dict[str, object]:
    return {
        "staff_id": staff_id,
        "event_type": StaffPayoutEventType.PAYOUT.value,
        "events": tuple(_event_payload(item) for item in events),
        "allocations": tuple(_allocation_payload(item) for item in allocations),
    }


def _allocation_payload(allocation) -> dict[str, object]:
    return {
        "bank_fact_identity": allocation.bank_fact_identity,
        "obligation_identity": allocation.obligation_identity,
        "amount_ntd": allocation.amount.amount,
    }


def _reopen_payload(event, links) -> dict[str, object]:
    return {
        "event": _event_payload(event),
        "links": tuple(_link_payload(item) for item in links),
    }


def _link_payload(link) -> dict[str, object]:
    return {
        "event_identity": link.event_identity,
        "obligation_identity": link.obligation_identity,
        "allocated_amount_ntd": link.allocated_amount.amount,
    }


def _event_payload(event) -> dict[str, object]:
    return {
        "identity": event.identity,
        "event_type": event.event_type.value,
        "status": event.status.value,
        "staff_id": event.staff_id,
        "amount_ntd": event.amount.amount,
        "finance_import_fact_identity": event.finance_import_fact_identity,
        "reversal_of_event_identity": event.reversal_of_event_identity,
    }


def _derived_event_identity(event_type, source_identity) -> str:
    digest = fingerprint_payload(
        {"event_type": event_type.value, "source_identity": source_identity}
    )
    return f"{event_type.value}:{digest.value}"


def _require_positive_money(value: MoneyNTD, field_name: str) -> None:
    if not isinstance(value, MoneyNTD):
        raise TypeError(f"{field_name} must be MoneyNTD")
    require_positive_integer(value.amount, field_name)


def _validate_identity(value: str, field_name: str) -> None:
    require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)


def _validate_optional_identity(value: str | None, field_name: str) -> None:
    if value is not None:
        _validate_identity(value, field_name)


def _validate_blockers(blockers: tuple[str, ...]) -> None:
    if not isinstance(blockers, tuple):
        raise TypeError("blocking anomalies must be a tuple")
    for blocker in blockers:
        _validate_identity(blocker, "blocking anomaly")
    if blockers != tuple(sorted(set(blockers))):
        raise ValueError("blocking anomalies must be sorted and unique")


def _require_event_type(event_type) -> None:
    if not isinstance(event_type, StaffPayoutEventType):
        raise TypeError("staff payout event type is invalid")
