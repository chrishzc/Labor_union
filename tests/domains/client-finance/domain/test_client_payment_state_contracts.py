"""Direct regression contracts for Client Finance payment aggregation rules."""

import pytest

from domains.client_finance.payment_transaction_state import calculate_client_payment_state


RECEIVABLES = {
    "deposit": "1000",
    "first_payment": "2000",
    "second_payment": "3000",
}


def _receipt(
    transaction_id: int,
    reference: str,
    amount: object,
    *,
    stage: str = "deposit",
    status: str = "succeeded",
    client_payment_id: int = 10,
    case_no: str = "CASE-100",
) -> dict[str, object]:
    return {
        "id": transaction_id,
        "external_reference": reference,
        "amount": amount,
        "stage": stage,
        "transaction_type": "receipt",
        "transaction_status": status,
        "reversal_of_transaction_id": None,
        "client_payment_id": client_payment_id,
        "case_no": case_no,
    }


def _reversal(
    transaction_id: int,
    reference: str,
    amount: object,
    receipt_id: int,
    *,
    stage: str = "deposit",
    status: str = "succeeded",
    client_payment_id: int = 10,
    case_no: str = "CASE-100",
) -> dict[str, object]:
    return {
        "id": transaction_id,
        "external_reference": reference,
        "amount": amount,
        "stage": stage,
        "transaction_type": "reversal",
        "transaction_status": status,
        "reversal_of_transaction_id": receipt_id,
        "client_payment_id": client_payment_id,
        "case_no": case_no,
    }


def test_payment_state_starts_zero_and_sums_succeeded_receipts_by_stage() -> None:
    assert calculate_client_payment_state(RECEIVABLES, []) == {
        "deposit_received": 0.0,
        "first_payment_received": 0.0,
        "second_payment_received": 0.0,
        "amount_received": 0.0,
    }

    state = calculate_client_payment_state(
        RECEIVABLES,
        [
            _receipt(1, "dep-1", "600"),
            _receipt(2, "first-1", "1200", stage="first_payment"),
            _receipt(3, "second-1", "2500", stage="second_payment"),
        ],
    )
    assert state == {
        "deposit_received": 600.0,
        "first_payment_received": 1200.0,
        "second_payment_received": 2500.0,
        "amount_received": 4300.0,
    }


def test_failed_receipt_does_not_change_net_received_amount() -> None:
    state = calculate_client_payment_state(
        RECEIVABLES,
        [_receipt(1, "dep-failed", "800", status="failed")],
    )
    assert state["deposit_received"] == 0.0
    assert state["amount_received"] == 0.0


def test_succeeded_reversal_reduces_original_receipt_but_failed_reversal_does_not() -> None:
    transactions = [
        _receipt(1, "dep-1", "800"),
        _reversal(2, "dep-rev-1", "300", 1),
        _reversal(3, "dep-rev-failed", "200", 1, status="failed"),
    ]

    state = calculate_client_payment_state(RECEIVABLES, transactions)
    assert state["deposit_received"] == 500.0
    assert state["amount_received"] == 500.0


def test_duplicate_external_reference_or_transaction_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="external_reference"):
        calculate_client_payment_state(
            RECEIVABLES,
            [_receipt(1, "same", "100"), _receipt(2, "same", "100")],
        )

    with pytest.raises(ValueError, match="duplicate transaction id"):
        calculate_client_payment_state(
            RECEIVABLES,
            [_receipt(1, "a", "100"), _receipt(1, "b", "100")],
        )


def test_reversal_must_reference_same_payment_case_and_stage() -> None:
    receipt = _receipt(1, "dep-1", "800")

    with pytest.raises(ValueError, match="same payment, case, and stage"):
        calculate_client_payment_state(
            RECEIVABLES,
            [receipt, _reversal(2, "wrong-stage", "100", 1, stage="first_payment")],
        )
    with pytest.raises(ValueError, match="same payment, case, and stage"):
        calculate_client_payment_state(
            RECEIVABLES,
            [receipt, _reversal(2, "wrong-payment", "100", 1, client_payment_id=11)],
        )
    with pytest.raises(ValueError, match="same payment, case, and stage"):
        calculate_client_payment_state(
            RECEIVABLES,
            [receipt, _reversal(2, "wrong-case", "100", 1, case_no="CASE-OTHER")],
        )


def test_succeeded_reversals_cannot_exceed_original_receipt() -> None:
    with pytest.raises(ValueError, match="exceed the original receipt"):
        calculate_client_payment_state(
            RECEIVABLES,
            [
                _receipt(1, "dep-1", "500"),
                _reversal(2, "dep-rev-1", "300", 1),
                _reversal(3, "dep-rev-2", "201", 1),
            ],
        )


def test_net_receipts_cannot_exceed_receivable_stage_amount() -> None:
    with pytest.raises(ValueError, match="outside the receivable range"):
        calculate_client_payment_state(
            RECEIVABLES,
            [_receipt(1, "dep-too-much", "1000.01")],
        )


def test_receivable_and_transaction_shapes_reject_invalid_numeric_or_identity_values() -> None:
    for invalid in (-1, True, "NaN"):
        bad = dict(RECEIVABLES)
        bad["deposit"] = invalid
        with pytest.raises(ValueError, match="receivable"):
            calculate_client_payment_state(bad, [])

    with pytest.raises(ValueError, match="all active receipt stages"):
        calculate_client_payment_state({"deposit": 1000}, [])
    with pytest.raises(TypeError, match="mappings"):
        calculate_client_payment_state(RECEIVABLES, ["not-a-transaction"])
    with pytest.raises(ValueError, match="external_reference"):
        calculate_client_payment_state(RECEIVABLES, [_receipt(1, " ", "100")])
    with pytest.raises(ValueError, match="unknown payment stage"):
        calculate_client_payment_state(
            RECEIVABLES,
            [_receipt(1, "unknown-stage", "100", stage="other")],
        )
