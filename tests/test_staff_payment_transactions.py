import pytest

from services.staff_payment_transactions import calculate_staff_payment_state


def test_failed_transfer_and_return_are_recalculated_as_net_paid_amount():
    state = calculate_staff_payment_state(1000, [
        {"external_reference": "t1", "transaction_type": "transfer", "transaction_status": "succeeded", "amount": 1000},
        {"external_reference": "t2", "transaction_type": "transfer", "transaction_status": "failed", "amount": 500},
        {"external_reference": "r1", "transaction_type": "return", "transaction_status": "succeeded", "amount": 250},
    ])
    assert state == {"amount_paid": 750.0, "payment_status": "partially_paid"}


def test_overpayment_is_rejected():
    with pytest.raises(ValueError, match="outside the payable range"):
        calculate_staff_payment_state(1000, [
            {"external_reference": "t1", "transaction_type": "transfer", "transaction_status": "succeeded", "amount": 1001},
        ])
