"""Finance-owned read contract for required second stages and valid settlements."""
from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SecondPaymentFinancialFacts:
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


class SecondPaymentQueryPort(Protocol):
    def get(self, case_no: str, *, lock: bool = False) -> SecondPaymentFinancialFacts | None: ...
    def settlement(self, case_no: str, identity: str, *, lock: bool = False) -> SecondPaymentFinancialFacts | None: ...
