"""Bounded Staff Payables accounting facts without a month filter."""
from dataclasses import dataclass


@dataclass(frozen=True)
class StaffAccountingItem:
    identity: str
    direction: str
    label: str
    party: str
    expected_ntd: int
    actual_ntd: int
    has_payment: bool
    version: str
    due_date: str | None
    summary_included: bool = True
    unallocated_surplus_ntd: int = 0


@dataclass(frozen=True)
class StaffAccountingTransaction:
    identity: str
    item_identity: str
    occurred_on: str
    kind: str
    amount_ntd: int
    bank: str | None
