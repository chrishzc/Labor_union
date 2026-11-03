"""Query and atomic reconciliation of a selected whole period."""
from dataclasses import dataclass
from datetime import date
from typing import Protocol, TypedDict

from domains.government_subsidy.period_reconciliation import (
    PeriodReconciliationConflict, SubsidyPeriod, SubsidyPeriodLine, require_exact_period_receipt, GovernmentPeriodBalance,
)


@dataclass(frozen=True, slots=True)
class PeriodCoverage:
    receipt_id: int
    period: SubsidyPeriod
    amount_ntd: int
    recovered_advance_ntd: int
    settled: bool = True


@dataclass(frozen=True, slots=True)
class SubsidyPeriodView:
    period: SubsidyPeriod
    version: int
    lines: tuple[SubsidyPeriodLine, ...]
    total_ntd: int | None
    coverage: tuple[PeriodCoverage, ...]
    blocked_cases: tuple[str, ...]
    recorded_lines: tuple[SubsidyPeriodLine, ...]
    changed_cases: tuple[str, ...]
    can_reconcile: bool
    balances: tuple[GovernmentPeriodBalance,...] = ()
    amount_controls: tuple['GovernmentAmountItem',...] = ()
    operations: tuple['GovernmentPeriodOperation',...] = ()
    amount_changes: tuple['GovernmentAmountChange',...] = ()


@dataclass(frozen=True)
class GovernmentAmountChange:
    case_no: str
    action: str
    before_ntd: int
    after_ntd: int
    computed_ntd: int
    reason: str
    actor: str
    confirmed_on: str


@dataclass(frozen=True)
class GovernmentAmountItem:
    case_no: str
    mode: str
    computed_ntd: int | None
    effective_ntd: int | None


@dataclass(frozen=True)
class GovernmentPeriodOperation:
    identity: int
    balance_identity: str
    action: str
    amount_ntd: int
    bank_row_id: int | None
    reason: str
    actor: str
    confirmed_on: str


@dataclass(frozen=True)
class GovernmentDifferenceCommand:
    period: SubsidyPeriod
    action: str
    identity: str
    amount_ntd: int | None
    bank_row_id: int | None
    handling: str
    reason: str
    expected_version: int
    key: str
    actor: str


class PeriodBankRow(TypedDict):
    id: int
    paid_on: date | None
    amount_ntd: int


class CasePeriodReceipt(TypedDict):
    receipt_id: int
    label: str
    amount_ntd: int
    recorded_case_amount_ntd: int
    recorded_service_end_date: date
    recovered_advance_ntd: int
    settled: bool


class CasePeriodCoverage(TypedDict):
    case_no: str
    service_end_date: date | None
    amount_ntd: int | None
    coverage: tuple[CasePeriodReceipt, ...]


class PeriodRepository(Protocol):
    def query(self, period: SubsidyPeriod, *, lock: bool = False) -> SubsidyPeriodView: ...
    def find_replay(self, key: str, command: tuple) -> int | None: ...
    def bank_amount(self, bank_row_id: int, *, reversal: bool = False) -> int: ...
    def save(self, view: SubsidyPeriodView, bank_row_id: int, key: str, actor: str) -> int: ...
    def reverse(self, receipt_id: int, bank_row_id: int, key: str, actor: str) -> int: ...
    def bank_rows(self) -> tuple[PeriodBankRow, ...]: ...
    def case_coverage(self, case_no: str) -> CasePeriodCoverage: ...


class PeriodReconciliationApplication:
    def __init__(self, repository: PeriodRepository, unit_of_work):
        self.repository = repository
        self.unit_of_work = unit_of_work

    def query(self, period: SubsidyPeriod) -> SubsidyPeriodView:
        return self.repository.query(period)

    def bank_rows(self) -> tuple[PeriodBankRow, ...]:
        return self.repository.bank_rows()

    def case_coverage(self, case_no: str) -> CasePeriodCoverage:
        return self.repository.case_coverage(case_no)

    def reconcile(self, period: SubsidyPeriod, bank_row_id: int, version: int, key: str, actor: str) -> int:
        with self.unit_of_work() as work:
            replay = self.repository.find_replay(key, (period.unit, period.year, period.index, bank_row_id, None))
            if replay is not None:
                work.commit()
                return replay
            current = self.repository.query(period, lock=True)
            if current.version != version:
                raise PeriodReconciliationConflict('subsidy_period_stale')
            if current.coverage:
                raise PeriodReconciliationConflict('subsidy_period_already_covered')
            if current.blocked_cases:
                raise PeriodReconciliationConflict('subsidy_case_already_covered')
            require_exact_period_receipt(current.lines, self.repository.bank_amount(bank_row_id))
            identity = self.repository.save(current, bank_row_id, key, actor)
            work.commit()
            return identity

    def reverse(self, receipt_id: int, bank_row_id: int, key: str, actor: str) -> int:
        with self.unit_of_work() as work:
            result = self.repository.reverse(receipt_id, bank_row_id, key, actor)
            work.commit()
            return result

    def difference(self,command: GovernmentDifferenceCommand):
        with self.unit_of_work() as work:
            result=self.repository.apply_difference(command)
            work.commit()
            return result
