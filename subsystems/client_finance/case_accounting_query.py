"""Bounded Client Finance accounting facts for the finance workspace."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ClientAccountingItem:
    identity: str
    direction: str
    label: str
    party: str
    expected_ntd: int
    actual_ntd: int
    has_payment: bool
    version: str
    due_date: str | None


@dataclass(frozen=True)
class ClientAccountingTransaction:
    identity: str
    item_identity: str
    occurred_on: str
    kind: str
    amount_ntd: int
    bank: str | None
