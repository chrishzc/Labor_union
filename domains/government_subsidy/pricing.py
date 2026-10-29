"""Government entitlement uses covered hours and the covered Payroll rate only."""

from decimal import Decimal


def subsidy_claim_amount(total_hours: Decimal, subsidy_cap: Decimal, covered_payroll_rate: int) -> int:
    if not total_hours.is_finite() or not subsidy_cap.is_finite() or min(total_hours, subsidy_cap) < 0:
        raise ValueError("government_subsidy_hours_invalid")
    amount = min(total_hours, subsidy_cap) * covered_payroll_rate
    if amount != amount.to_integral_value():
        raise ValueError("government_subsidy_amount_not_integer")
    return int(amount)
