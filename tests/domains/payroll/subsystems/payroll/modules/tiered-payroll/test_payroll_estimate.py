"""Candidate estimates reuse Payroll tiers and funding dates without obligations."""
from datetime import date
from decimal import Decimal

import pytest

from domains.payroll.estimate import estimate_service_pay
from domains.payroll.tiered_rates import TieredPayrollRate
from shared_kernel.money import MoneyNTD


def test_preliminary_estimate_uses_agreed_quantity_not_fictitious_assignment_dates():
    result = estimate_service_pay(TieredPayrollRate(300, 380, Decimal(40), False),
        20, Decimal(8), MoneyNTD(1000), date(2026, 12, 31))
    assert result.total.amount == 58600
    assert [(part.amount, part.due_date) for part in result.installments] == [(58600, date(2027, 1, 15))]


def test_social_salary_estimate_retains_different_payroll_funding_payment_dates():
    result = estimate_service_pay(TieredPayrollRate(350, 380, Decimal(120), True),
        20, Decimal(8), MoneyNTD(500), date(2026, 12, 31))
    assert result.total.amount == 57700
    assert [(part.funding_kind, part.amount, part.due_date) for part in result.installments] == [
        ('client', 15700, date(2027, 1, 15)), ('subsidy', 42000, date(2027, 2, 15))]


def test_unconfirmed_end_does_not_invent_a_payment_date():
    result = estimate_service_pay(TieredPayrollRate(300, 300, Decimal(0), False),
        1, Decimal('8.5'), MoneyNTD(0), None)
    assert result.total.amount == 2550 and result.installments[0].due_date is None


def test_fractional_ntd_is_not_silently_rounded_in_staff_offers():
    with pytest.raises(ValueError, match='whole_ntd'):
        estimate_service_pay(TieredPayrollRate(301, 301, Decimal(0), False), 1, Decimal('8.5'), MoneyNTD(0), None)
