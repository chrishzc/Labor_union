import pytest

from services.order_amount_calculator import calculate_order_amounts


SCHEDULE = {"deposit_service_days": 5, "deposit_due_date": "2026-04-01"}


def _terms(case_no, identity_status, service_days=20, hours_per_day=9, floor_fee=0):
    return {
        "case_no": case_no,
        "service_days": service_days,
        "service_hours_per_day": hours_per_day,
        "identity_status": identity_status,
        "client_floor_fee": floor_fee,
        "service_start_date": "2026-05-01",
        "actual_completion_date": "2026-05-20",
    }


def test_non_citizen_uses_350_rate_and_leaves_second_date_pending_first_receipt():
    result = calculate_order_amounts(
        _terms("115000001", "非市民", service_days=36, floor_fee=900),
        [{"assignment_id": 1, "staff_id": 7, "actual_hours": 324, "hourly_rate": 350, "floor_fee_amount": 900}],
        SCHEDULE,
    )

    assert result["client_ledger_plan"]["stages"] == [
        {"stage": "deposit", "service_days": 5, "receivable": 16650, "received": 0, "due_date": "2026-04-01", "received_at": None},
        {"stage": "first_payment", "service_days": 15, "receivable": 47250, "received": 0, "due_date": "2026-05-01", "received_at": None},
        {"stage": "second_payment", "service_days": 16, "receivable": 50400, "received": 0, "due_date": None, "received_at": None},
    ]
    assert result["client_ledger_plan"]["amount_receivable"] == 114300
    assert result["subsidy_plan"]["subsidy_claim_amount"] == 0


def test_general_citizen_claim_uses_40_hours_times_staff_service_price():
    result = calculate_order_amounts(
        _terms("115000002", "一般市民"),
        [{"assignment_id": 2, "staff_id": 8, "actual_hours": 180, "hourly_rate": 350, "floor_fee_amount": 0}],
        SCHEDULE,
    )

    assert result["client_ledger_plan"]["amount_receivable"] == 54000
    assert result["client_ledger_plan"]["subsidy_return_amount"] == 12000
    assert result["subsidy_plan"]["subsidy_claim_amount"] == 14000
    assert result["subsidy_plan"]["staff_allocations"] == [{
        "assignment_id": 2, "staff_id": 8, "subsidy_hours": 40,
        "service_unit_price": 350, "subsidy_claim_amount": 14000,
    }]


def test_full_subsidy_has_zero_client_receivable_and_second_payment_date_is_empty():
    result = calculate_order_amounts(
        _terms("115000003", "補助市民", hours_per_day=6),
        [{"assignment_id": 3, "staff_id": 9, "actual_hours": 120, "hourly_rate": 350, "floor_fee_amount": 0}],
        SCHEDULE,
    )

    assert result["client_ledger_plan"]["amount_receivable"] == 0
    assert result["client_ledger_plan"]["subsidy_return_amount"] == 0
    assert result["client_ledger_plan"]["stages"][2]["service_days"] == 0
    assert result["client_ledger_plan"]["stages"][2]["due_date"] is None
    assert result["staff_payment_plans"][0]["due_date"] == "2026-07-15"
    assert result["subsidy_plan"]["subsidy_claim_amount"] == 42000


def test_claim_amount_is_weighted_by_each_staff_actual_hours_and_rate():
    result = calculate_order_amounts(
        _terms("115000004", "一般市民", floor_fee=900),
        [
            {"assignment_id": 4, "staff_id": 7, "actual_hours": 45, "hourly_rate": 300, "floor_fee_amount": 300},
            {"assignment_id": 5, "staff_id": 9, "actual_hours": 135, "hourly_rate": 400, "floor_fee_amount": 600},
        ],
        SCHEDULE,
    )

    assert result["staff_payment_plans"][0]["total_payable"] == 13800
    assert result["staff_payment_plans"][1]["total_payable"] == 54600
    assert result["subsidy_plan"]["staff_allocations"] == [
        {"assignment_id": 4, "staff_id": 7, "subsidy_hours": 10, "service_unit_price": 300, "subsidy_claim_amount": 3000},
        {"assignment_id": 5, "staff_id": 9, "subsidy_hours": 30, "service_unit_price": 400, "subsidy_claim_amount": 12000},
    ]
    assert result["subsidy_plan"]["subsidy_claim_amount"] == 15000


def test_claim_stays_unready_until_staff_actual_hours_and_rates_exist():
    result = calculate_order_amounts(_terms("115000005", "一般市民"), [], SCHEDULE)

    assert result["subsidy_plan"]["claim_amount_ready"] is False
    assert result["subsidy_plan"]["subsidy_claim_amount"] is None


def test_subsidy_hours_are_capped_by_total_service_hours():
    result = calculate_order_amounts(
        _terms("115000008", "一般市民", service_days=3, hours_per_day=9),
        [{"assignment_id": 8, "staff_id": 10, "actual_hours": 27, "hourly_rate": 350}],
        {"deposit_service_days": 1, "deposit_due_date": "2026-04-01"},
    )

    assert result["subsidy_plan"]["subsidy_hours"] == 27
    assert result["subsidy_plan"]["subsidy_claim_amount"] == 9450


def test_rejects_unknown_identity_status_and_missing_deposit_date():
    with pytest.raises(ValueError, match="unsupported identity_status"):
        calculate_order_amounts(_terms("115000006", "未知"), [], SCHEDULE)
    with pytest.raises(ValueError, match="deposit_due_date"):
        calculate_order_amounts(_terms("115000007", "一般市民"), [], {"deposit_service_days": 5})


def test_identity_status_is_returned_with_the_calculation_plan():
    result = calculate_order_amounts(
        _terms("115000009", "一般市民"),
        [{"assignment_id": 9, "staff_id": 11, "actual_hours": 180, "hourly_rate": 350}],
        SCHEDULE,
    )

    assert result["identity_status"] == "一般市民"
