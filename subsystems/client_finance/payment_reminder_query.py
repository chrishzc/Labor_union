"""Typed current payment facts for LINE reminder scheduling; no ledger writes."""
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from subsystems.client_finance.overdue_payment_query import OverdueClientPayment


@dataclass(frozen=True, slots=True)
class ClientPaymentReminderFacts:
    payment: OverdueClientPayment
    service_start_date: date | None
    contract_completed: bool
    case_status: str


class ClientPaymentReminderQueryPort(Protocol):
    def candidates(self, day: date, after: str = '', limit: int = 100) -> tuple[ClientPaymentReminderFacts, ...]: ...
    def get(self, identity: str, *, lock: bool = False) -> ClientPaymentReminderFacts | None: ...
