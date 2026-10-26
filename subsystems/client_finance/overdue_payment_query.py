"""Finance-owned, read-only facts for each independently overdue payment stage."""
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

PaymentStage = Literal['deposit', 'first', 'second']


@dataclass(frozen=True, slots=True)
class OverdueClientPayment:
    case_no: str
    payment_stage: PaymentStage
    obligation_identity: str
    projection_version: int
    obligation_event_id: int
    due_date: date
    remaining_amount_ntd: int

    def overdue_on(self, day: date) -> bool:
        return self.due_date < day and self.remaining_amount_ntd > 0


class OverduePaymentQueryPort(Protocol):
    def list(self, day: date, page: int, page_size: int) -> tuple[tuple[OverdueClientPayment, ...], int]: ...
    def get(self, identity: str, *, lock: bool = False) -> OverdueClientPayment | None: ...
