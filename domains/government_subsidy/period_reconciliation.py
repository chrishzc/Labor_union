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
