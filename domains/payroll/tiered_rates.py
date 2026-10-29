"""Assignment-owned salary tiers and funding-specific payment months."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TieredPayrollRate:
    covered_rate: int
    excess_rate: int
    subsidy_hours: Decimal
    directly_subsidized: bool

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in (self.covered_rate, self.excess_rate)):
            raise ValueError("payroll_tiered_rate_invalid")
        if not self.subsidy_hours.is_finite() or self.subsidy_hours < 0:
            raise ValueError("payroll_subsidy_hours_invalid")


def funding_due_date(completed_on: date, *, directly_subsidized: bool) -> date:
    months = 2 if directly_subsidized else 1
    index = completed_on.month - 1 + months
    return date(completed_on.year + index // 12, index % 12 + 1, 15)


def price_hours(days: tuple[tuple[Decimal, bool], ...], rate: TieredPayrollRate, consumed=Decimal(0)) -> tuple[int, int]:
    covered_amount = Decimal(0)
    excess_amount = Decimal(0)
    for hours, double_pay in days:
        covered = min(hours, max(Decimal(0), rate.subsidy_hours - consumed))
        multiplier = 2 if double_pay else 1
        covered_amount += covered * rate.covered_rate * multiplier
        excess_amount += (hours - covered) * rate.excess_rate * multiplier
        consumed += hours
    if any(value != value.to_integral_value() for value in (covered_amount, excess_amount)):
        raise ValueError("payroll_tiered_amount_must_be_whole_ntd")
    return int(covered_amount), int(excess_amount)
