"""Finance-owned read contract for first-stage receipts and valid settlements."""
from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FirstPaymentFinancialFacts:
    case_no: str
    obligation_identity: str
    account_version: int
    obligation_event_id: int
    due_date: date
    required_amount: int
    remaining_amount: int
    settled: bool
    settlement_identity: str | None = None
    settled_amount: int = 0


class FirstPaymentQueryPort(Protocol):
    def get(self, case_no: str, *, lock: bool = False) -> FirstPaymentFinancialFacts | None: ...
    def settlement(self, case_no: str, identity: str, *, lock: bool = False) -> FirstPaymentFinancialFacts | None: ...
