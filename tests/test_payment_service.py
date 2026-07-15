import pytest

from services.payment_service import calculate_staff_payable


def test_staff_payable_keeps_salary_and_floor_fee_separate():
    result = calculate_staff_payable(45, 350, 300, -50)
    assert result == {
        "service_hours": 45.0, "hourly_rate": 350.0, "service_salary": 15750.0,
        "floor_fee_amount": 300.0, "adjustment_amount": -50.0, "total_payable": 16000.0,
    }


def test_staff_payable_rejects_negative_total():
    with pytest.raises(ValueError, match="total payable"):
        calculate_staff_payable(1, 0, 0, -1)
