from datetime import date
from decimal import Decimal

from scripts.backfill_canonical_accounting_projections import (
    LEGACY_CLIENT_STAGE_MAP,
    _is_native_mysql_dump,
    _validate_backup,
    build_client_open_obligations,
    build_staff_open_obligations,
)


def _client_payment(**overrides):
    row = {
        "case_no": "C-1",
        "deposit_receivable": Decimal("1000"), "deposit_received": Decimal("1000"), "deposit_due_date": date(2026, 6, 15),
        "first_receivable": Decimal("2000"), "first_received": Decimal("500"), "first_due_date": date(2026, 7, 15),
        "second_receivable": Decimal("3000"), "second_received": Decimal("0"), "second_due_date": None,
        "subsidy_refund_receivable": Decimal("999999"),
    }
    row.update(overrides)
    return row


def test_client_backfill_uses_verified_service_receivable_stages_not_legacy_subsidy_columns():
    items, review_keys = build_client_open_obligations(
        [_client_payment()],
        {("C-1", "deposit"): 1000, ("C-1", "first"): 500},
    )

    assert [(item.stage, item.amount_due_ntd, item.due_date) for item in items] == [
        ("first", 1500, date(2026, 7, 15)),
        ("second", 3000, None),
    ]
    assert review_keys == ()


def test_client_backfill_sends_snapshot_disagreement_to_review_without_creating_an_obligation():
    items, review_keys = build_client_open_obligations(
        [_client_payment()],
        {("C-1", "deposit"): 999, ("C-1", "first"): 500},
    )

    assert [item.stage for item in items] == ["first", "second"]
    assert review_keys == ("C-1:deposit:transaction_snapshot_mismatch",)


def test_legacy_transaction_stage_names_map_to_canonical_obligation_stages():
    assert LEGACY_CLIENT_STAGE_MAP == {
        "deposit": "deposit",
        "first_payment": "first",
        "second_payment": "second",
    }


def test_staff_backfill_accepts_only_unpaid_integer_pending_obligation_and_marks_fractional_for_review():
    rows = [
        {"id": 1, "assignment_id": 10, "case_no": "C-1", "staff_id": 8, "total_payable": Decimal("20000"), "amount_paid": Decimal("0"), "due_date": date(2026, 8, 14), "actual_end_date": date(2026, 8, 14), "client_service_fee_total": Decimal("100"), "client_identity_status": "補助市民", "service_days": 20, "service_hours_per_day": 6, "floor_fee": 0, "payment_status": "pending"},
        {"id": 2, "assignment_id": 11, "case_no": "C-2", "staff_id": 9, "total_payable": Decimal("20000.50"), "amount_paid": Decimal("0"), "due_date": date(2026, 8, 15), "actual_end_date": date(2026, 8, 15), "client_service_fee_total": Decimal("100"), "client_identity_status": "一般市民", "service_days": 20, "service_hours_per_day": 9, "floor_fee": 0, "payment_status": "pending"},
        {"id": 3, "assignment_id": 12, "case_no": "C-3", "staff_id": 10, "total_payable": Decimal("20000"), "amount_paid": Decimal("1"), "due_date": date(2026, 8, 15), "actual_end_date": date(2026, 8, 15), "client_service_fee_total": Decimal("100"), "client_identity_status": "一般市民", "service_days": 20, "service_hours_per_day": 9, "floor_fee": 0, "payment_status": "pending"},
    ]

    items, review_ids = build_staff_open_obligations(rows)

    assert [(item.staff_payment_id, item.amount_due_ntd, item.due_date) for item in items] == [(1, 20000, date(2026, 9, 15))]
    assert review_ids == (2, 3)


def test_staff_backfill_routes_unknown_legacy_identity_to_review():
    items, review_ids = build_staff_open_obligations([{
        "id": 4, "assignment_id": 13, "case_no": "C-4", "staff_id": 11,
        "total_payable": Decimal("20000"), "amount_paid": Decimal("0"),
        "actual_end_date": date(2026, 8, 15), "client_service_fee_total": Decimal("0"),
        "client_identity_status": "歷史未知", "service_days": 20,
        "service_hours_per_day": 6, "floor_fee": 0, "payment_status": "pending",
    }])

    assert items == ()
    assert review_ids == (4,)


def test_native_dump_recognition_rejects_utf16_text():
    assert _is_native_mysql_dump(b"-- MySQL dump 10.13\n")
    assert not _is_native_mysql_dump("-- MySQL dump 10.13\n".encode("utf-16"))
