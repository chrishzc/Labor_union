from datetime import date

import pytest

from domains.payroll.payment_due_date import calculate_staff_payment_due_date


def test_client_fee_case_is_due_on_next_calendar_month_fifteenth():
    assert calculate_staff_payment_due_date(date(2026, 8, 31), 1, False) == date(2026, 9, 15)


def test_full_subsidy_case_is_due_on_second_calendar_month_fifteenth():
    assert calculate_staff_payment_due_date(date(2026, 11, 30), 0, True) == date(2027, 1, 15)


def test_zero_client_payable_requires_full_subsidy_order():
    with pytest.raises(ValueError, match="full subsidy"):
        calculate_staff_payment_due_date(date(2026, 8, 1), 0, False)
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_staff_payment_due_date(date(2026, 8, 1), -1, False)
