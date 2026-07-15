from services.payment_rules import evaluate_payment_boundary


def test_finalized_assignments_reject_overallocated_floor_fee():
    result = evaluate_payment_boundary(
        "assignment_allocation",
        order_hours=180,
        floor_fee=900,
        finalized=True,
        assignments=[
            {"staff_id": 7, "hours": 45, "floor_fee": 900},
            {"staff_id": 9, "hours": 135, "floor_fee": 1},
        ],
    )
    assert result == {"valid": False, "error": "allocated floor fee exceeds order floor fee"}


def test_same_staff_can_have_multiple_pending_cases():
    result = evaluate_payment_boundary(
        "staff_portfolio",
        staff_id=7,
        payments=[
            {"case_no": "115000001", "status": "pending"},
            {"case_no": "115000002", "status": "partially_paid"},
            {"case_no": "115000001", "status": "paid"},
        ],
    )
    assert result == {"valid": True, "pending_payment_count": 2, "case_count": 2}


def test_failed_and_reversed_transactions_do_not_inflate_net_amount():
    result = evaluate_payment_boundary(
        "transaction_net",
        positive_types=["receipt"],
        negative_types=["reversal"],
        transactions=[
            {"external_reference": "receipt-1", "transaction_type": "receipt", "transaction_status": "succeeded", "amount": 1000},
            {"external_reference": "failed-1", "transaction_type": "receipt", "transaction_status": "failed", "amount": 500},
            {"external_reference": "reversal-1", "transaction_type": "reversal", "transaction_status": "succeeded", "amount": 1000},
        ],
    )
    assert result == {"valid": True, "net_amount": 0}


def test_duplicate_external_reference_is_rejected():
    result = evaluate_payment_boundary(
        "transaction_net",
        positive_types=["transfer"],
        negative_types=["return"],
        transactions=[
            {"external_reference": "bank-1", "transaction_type": "transfer", "transaction_status": "succeeded", "amount": 500},
            {"external_reference": "bank-1", "transaction_type": "return", "transaction_status": "succeeded", "amount": 500},
        ],
    )
    assert result == {"valid": False, "error": "transaction 2 has duplicate or empty external_reference"}
