"""Whole-period government receipts; case lines are evidence, never cash allocations."""
from dataclasses import dataclass
from datetime import date
from typing import Literal


class PeriodReconciliationConflict(ValueError):
    """A closed business conflict; callers return 409 and refresh current facts."""


@dataclass(frozen=True, slots=True)
class SubsidyPeriod:
    unit: Literal['month', 'quarter', 'year']
    year: int
    index: int

    def __post_init__(self):
        maximum = {'month': 12, 'quarter': 4, 'year': 1}.get(self.unit)
        if maximum is None or not 1912 <= self.year <= 9998 or not 1 <= self.index <= maximum:
            raise ValueError('subsidy_period_invalid')

    @property
    def start(self) -> date:
        month = self.index if self.unit == 'month' else (self.index - 1) * 3 + 1 if self.unit == 'quarter' else 1
        return date(self.year, month, 1)

    @property
    def end(self) -> date:
        months = {'month': 1, 'quarter': 3, 'year': 12}[self.unit]
        month = self.start.month + months
        return date(self.year + (month - 1) // 12, (month - 1) % 12 + 1, 1)

    @property
    def label(self) -> str:
        suffix = f'{self.index} 月' if self.unit == 'month' else f'第 {self.index} 季' if self.unit == 'quarter' else '全年'
        return f'{self.year} 年 {suffix}'

    def contains(self, value: date) -> bool:
        return self.start <= value < self.end

    def overlaps(self, other: 'SubsidyPeriod') -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True, slots=True)
class SubsidyPeriodLine:
    case_no: str
    service_end_date: date
    amount_ntd: int | None
    unavailable_reason: str | None


def require_exact_period_receipt(lines: tuple[SubsidyPeriodLine, ...], amount_ntd: int) -> int:
    if not lines or any(line.amount_ntd is None for line in lines):
        raise PeriodReconciliationConflict('subsidy_period_incomplete')
    if len({line.case_no.casefold() for line in lines}) != len(lines):
        raise PeriodReconciliationConflict('subsidy_period_duplicate_case')
    total = sum(line.amount_ntd for line in lines)
    if total <= 0 or amount_ntd != total:
        raise PeriodReconciliationConflict('subsidy_period_amount_mismatch')
    return total


@dataclass(frozen=True)
class GovernmentPeriodBalance:
    identity: str
    root_receipt_id: int
    kind: str
    case_no: str | None
    direction: str
    expected_ntd: int
    received_ntd: int
    recognized_ntd: int
    returned_ntd: int

    @property
    def remaining_ntd(self):
        return max(0,self.expected_ntd-self.received_ntd-self.recognized_ntd)

    @property
    def refund_due_ntd(self):
        return max(0,self.received_ntd-self.expected_ntd-self.returned_ntd) if self.direction=='receivable' else 0

    @property
    def settled(self):
        return not self.remaining_ntd and not self.refund_due_ntd

    @property
    def status(self):
        if self.refund_due_ntd:
            return '多撥待退回'
        if self.remaining_ntd:
            return '待補撥' if self.direction=='receivable' else '待退回'
        return '已作損失處理' if self.recognized_ntd else '已結清'


def require_government_initial_receipt(lines,amount,handling):
    if not lines or any(line.amount_ntd is None for line in lines):
        raise PeriodReconciliationConflict('subsidy_period_incomplete')
    total=sum(line.amount_ntd for line in lines)
    if total<=0 or amount<=0:
        raise PeriodReconciliationConflict('subsidy_period_amount_invalid')
    expected='exact' if amount==total else 'partial' if amount<total else 'refund_excess'
    if handling!=expected:
        raise PeriodReconciliationConflict('subsidy_period_handling_required')
    return total


def require_government_balance_action(balance,action,amount,reason):
    if not isinstance(amount,int) or isinstance(amount,bool) or amount<=0:
        raise PeriodReconciliationConflict('subsidy_period_amount_invalid')
    if action=='loss':
        if balance.direction!='receivable' or amount>balance.remaining_ntd or not reason.strip():
            raise PeriodReconciliationConflict('subsidy_period_loss_invalid')
    elif action=='refund':
        limit=balance.refund_due_ntd if balance.direction=='receivable' else balance.remaining_ntd
        if amount>limit:
            raise PeriodReconciliationConflict('subsidy_period_refund_exceeded')
    elif action=='receipt':
        if balance.direction!='receivable':
            raise PeriodReconciliationConflict('subsidy_period_receipt_invalid')
    else:
        raise PeriodReconciliationConflict('subsidy_period_action_invalid')
