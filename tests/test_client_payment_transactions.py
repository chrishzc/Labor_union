import pytest

from services.client_payment_transactions import calculate_client_payment_state


@pytest.mark.parametrize("stage", ["subsidy_refund", "subsidy_return"])
def test_refund_and_subsidy_return_are_not_active_payment_stages(stage):
    with pytest.raises(ValueError, match="unknown payment stage"):
        calculate_client_payment_state(
        {"deposit": 1000, "first_payment": 2000, "second_payment": 3000, "subsidy_refund": 1200},
        [
            {"external_reference": "d", "stage": "deposit", "transaction_type": "receipt", "transaction_status": "succeeded", "amount": 1000},
            {"external_reference": "f", "stage": "first_payment", "transaction_type": "receipt", "transaction_status": "failed", "amount": 2000},
            {"external_reference": "r", "stage": stage, "transaction_type": "refund", "transaction_status": "succeeded", "amount": 1200},
        ],
        )


def test_receipts_and_failed_transactions_are_aggregated_by_active_stage():
    state = calculate_client_payment_state(
        {"deposit": 1000, "first_payment": 2000, "second_payment": 3000},
        [
            {"external_reference": "d", "stage": "deposit", "transaction_type": "receipt", "transaction_status": "succeeded", "amount": 1000},
            {"external_reference": "f", "stage": "first_payment", "transaction_type": "receipt", "transaction_status": "failed", "amount": 2000},
        ],
    )
    assert state == {
        "deposit_received": 1000.0,
        "first_payment_received": 0.0,
        "second_payment_received": 0.0,
        "amount_received": 1000.0,
    }
