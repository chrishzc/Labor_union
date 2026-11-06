"""Human Payroll correction, with Staff Payables coordination in the same UoW."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PayrollAmountCommand:
    case_no: str
    identity: str
    action: str
    amount_ntd: int | None
    reason: str
    expected_version: int
    key: str
    actor: str


@dataclass(frozen=True)
class HistoricalUnpaidPayableCommand:
    case_no: str
    staff_id: int
    obligation_identity: str | None
    expected_event_id: int | None
    amount_ntd: int
    due_date: date | None
    evidence: str
    key: str
    actor: str


@dataclass(frozen=True)
class PayrollAmountItem:
    identity: str
    party: str
    mode: str
    computed_ntd: int
    effective_ntd: int
    actual_ntd: int
    remaining_ntd: int


@dataclass(frozen=True)
class PayrollAmountEvent:
    identity: str
    target_identity: str
    action: str
    before_ntd: int
    after_ntd: int
    computed_ntd: int
    reason: str
    actor: str
    confirmed_on: str


@dataclass(frozen=True)
class PayrollAmountView:
    case_no: str
    version: int
    items: tuple[PayrollAmountItem,...]
    events: tuple[PayrollAmountEvent,...]


class PayrollAmountApplication:
    def __init__(self,repository,unit_of_work):
        self.repository,self.unit_of_work=repository,unit_of_work

    def query(self,case_no):
        return self.repository.query(case_no)

    def apply(self,command):
        with self.unit_of_work() as work:
            result=self.repository.replay(command)
            if result is None:
                result=self.repository.apply(command)
            work.commit()
            return result

    def record_historical_unpaid(self, command: HistoricalUnpaidPayableCommand) -> str:
        with self.unit_of_work() as work:
            identity = self.repository.record_historical_unpaid(command)
            work.commit()
            return identity
