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
    settled: bool = False
    recognized_ntd: int = 0

    @property
    def remaining_ntd(self):
        return 0 if self.settled else max(0, self.expected_ntd - self.actual_ntd - self.recognized_ntd)

    @property
    def noncash_ntd(self):
        return max(self.recognized_ntd, max(0, self.expected_ntd - self.actual_ntd) if self.settled else 0)


@dataclass(frozen=True)
class ClientAccountingTransaction:
    identity: str
    item_identity: str
    occurred_on: str
    kind: str
    amount_ntd: int
    bank: str | None
