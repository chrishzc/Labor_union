from decimal import Decimal

from scripts.imports.import_finance_excel import allocate_receipt, build_snapshot_plan


def _order(**overrides):
    order = {
        "case_no": "115000001",
        "service_days": 20,
        "service_hours_per_day": 9,
        "subsidy_eligibility": "一般市民",
        "floor_fee": 600,
        "deposit_date": "2026-04-01",
        "deposit_service_days": 5,
        "start_date": "2026-05-01",
        "actual_start_date": None,
        "actual_end_date": None,
    }
    order.update(overrides)
    return order


def test_snapshot_plan_uses_order_service_terms_not_import_amount():
    plan = build_snapshot_plan(_order())

    stages = plan["client_ledger_plan"]["stages"]
    assert [stage["receivable"] for stage in stages] == [14100, 40500, 0]
    assert plan["client_ledger_plan"]["amount_receivable"] == 54600
    assert stages[1]["due_date"] == "2026-05-01"


def test_missing_deposit_service_days_skips_snapshot_creation():
    assert build_snapshot_plan(_order(deposit_service_days=None)) is None


def test_receipt_allocation_follows_three_collection_stages():
    allocations = allocate_receipt(
        {"deposit": 1000, "first_payment": 2000, "second_payment": 3000},
        {"deposit_received": 800, "first_payment_received": 0, "second_payment_received": 0},
        Decimal("1500"),
    )

    assert allocations == [("deposit", Decimal("200")), ("first_payment", Decimal("1300"))]
