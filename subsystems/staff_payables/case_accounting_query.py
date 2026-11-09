"""Bounded Staff Payables accounting facts without a month filter."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class StaffFundingPortion:
    funding_kind: str
    amount_ntd: int
    due_date: date | None
    settled_ntd: int | None
    remaining_ntd: int | None


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
    settled: bool = False
    recognized_ntd: int = 0
    funding_portions: tuple[StaffFundingPortion, ...] = ()

    @property
    def remaining_ntd(self):
        return 0 if self.settled else max(0, self.expected_ntd - self.actual_ntd - self.recognized_ntd)

    @property
    def noncash_ntd(self):
        return max(self.recognized_ntd,max(0, self.expected_ntd - self.actual_ntd) if self.settled else 0)


@dataclass(frozen=True)
class StaffAccountingTransaction:
    identity: str
    item_identity: str
    occurred_on: str
    kind: str
    amount_ntd: int
    bank: str | None
    bank_amount_ntd: int | None = None
    transfer_fee_ntd: int | None = None
