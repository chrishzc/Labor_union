"""Typed, read-only projection of the existing deposit obligation and settlement."""
from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DepositPayment:
    case_no: str
    obligation_identity: str
    obligation_version: int
    amount_ntd: int
    due_date: date | None
    virtual_account: str | None
    settlement_identity: str | None
    received_on: date | None

    @property
    def settled(self) -> bool:
        return self.settlement_identity is not None


class DepositPaymentQueryPort(Protocol):
    def get(self, case_no: str, *, lock: bool = False) -> DepositPayment | None: ...
