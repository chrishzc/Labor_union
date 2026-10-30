"""Read-only service-quantity estimates; these never constitute an obligation."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from domains.payroll.installments import PayrollInstallment
from domains.payroll.tiered_rates import TieredPayrollRate, price_hours, funding_due_date
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_positive_integer, require_positive_half_hour


@dataclass(frozen=True)
class PayrollEstimate:
    total: MoneyNTD
    installments: tuple[PayrollInstallment, ...]


def estimate_service_pay(rate: TieredPayrollRate, service_days: int, hours_per_day: Decimal,
                         floor_fee: MoneyNTD, planned_end: date | None) -> PayrollEstimate:
    require_positive_integer(service_days, 'estimated service days')
    require_positive_half_hour(hours_per_day, 'estimated hours per day')
    if floor_fee.amount < 0:
        raise ValueError('estimated floor fee must not be negative')
    # Quantity-only estimate: no fictitious assignment or service dates are created.
    covered, excess = price_hours(tuple((hours_per_day, False) for _ in range(service_days)), rate)
    total = covered + excess + floor_fee.amount
    subsidy = covered if rate.directly_subsidized else 0
    portions = tuple(PayrollInstallment(kind, amount,
        funding_due_date(planned_end, directly_subsidized=kind == 'subsidy') if planned_end else None)
        for kind, amount in (('client', total - subsidy), ('subsidy', subsidy)) if amount > 0)
    return PayrollEstimate(MoneyNTD(total), portions)
