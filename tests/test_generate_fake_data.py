import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from scripts.generate_fake_data import (
    BOUNDARY_CASES,
    BOUNDARY_SERVICE_DAYS,
    _assign_available_staff,
    _clear_generator_owned_demo_data,
    _finance_duplicate_normalized_result,
    _prorate_amount,
    _schedule_end_date,
    _schedule_rows_for_segment,
    _schedule_start_for_completed_service,
    _segment_work_day_counts,
    build_lifecycle_fixture_plan,
    fixture_admin_note,
    parse_cli_args,
)
from services.finance_transaction_fingerprint import build_dedup_fingerprint


def test_boundary_overlays_preserve_a_mixed_lifecycle_plan():
    case_nos = [f"1150000{number:02d}" for number in range(1, 51)]
    plan = build_lifecycle_fixture_plan(case_nos, seed=20260722)

    assert set(plan) == set(case_nos)
    assert plan["115000003"]["scenario"] == "in_service"
    assert plan["115000004"]["scenario"] == "closed"
    assert plan["115000005"]["scenario"] == "cancelled"
    assert {plan[case_no]["scenario"] for case_no in case_nos} >= {
        "new_inquiry", "matching_in_progress", "deposit_received",
        "in_service", "completed_pending_settlement", "closed", "cancelled",
    }
    assert len([case_no for case_no in case_nos if plan[case_no]["boundary_type"] == "none"]) == 50 - len(BOUNDARY_CASES)


def test_admin_note_has_the_standard_boundary_keys():
    note = fixture_admin_note("first_payment_partial_then_overpay", "three receipts total 3000 for receivable 2500")

    assert note.startswith("fixture_type=boundary;")
    assert "boundary_type=first_payment_partial_then_overpay" in note
    assert "owner_module=GenerateFakeData" in note
    assert "expected=three receipts total 3000 for receivable 2500" in note
    assert fixture_admin_note("none") == "fixture_type=normal; boundary_type=none"


def test_seed_db_flags_are_opt_in(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["generate_fake_data.py", "--seed-db", "--replace-demo-db"])

    args = parse_cli_args()

    assert args.seed_db is True
    assert args.replace_demo_db is True


def test_demo_reset_never_touches_legacy_payments():
    class Cursor:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)

    cursor = Cursor()
    _clear_generator_owned_demo_data(cursor)

    assert "DELETE FROM payments" not in cursor.statements
    assert cursor.statements[-1] == "DELETE FROM clients"


def test_seed_source_keeps_alert_tables_out_of_the_generator():
    source = Path("scripts/generate_fake_data.py").read_text(encoding="utf-8")

    assert "INSERT INTO finance_alerts" not in source
    assert "INSERT INTO finance_alert_events" not in source
    assert "finance_alert_detection" not in source
    assert "LIKE '%[lifecycle_fixture]%'" not in source
    assert "NOT LIKE 'fixture_type=%; boundary_type=%'" not in source


def test_completed_service_window_never_ends_after_reference_date():
    reference_date = date(2026, 7, 22)

    start, end = _schedule_start_for_completed_service(
        reference_date, 25, "週休2日"
    )

    assert start <= end <= reference_date
    assert _schedule_end_date(start, 25, "週休2日") == end


def test_staff_assignment_preserves_requested_window():
    class Cursor:
        def __init__(self):
            self.params = None

        def execute(self, _statement, params):
            self.params = params

        def fetchone(self):
            return {"count": 1 if self.params[0] == 1 else 0}

    cursor = Cursor()
    start = date(2026, 6, 1)
    end = date(2026, 6, 30)

    assert _assign_available_staff(cursor, [1, 2], start, end) == 2
    assert cursor.params == (2, start, end, 2, end, start)


def test_fixed_handoff_cases_have_exact_work_day_segments():
    assert BOUNDARY_SERVICE_DAYS == {
        "115000003": 20,
        "115000004": 25,
        "115000008": 30,
        "115000009": 30,
    }
    assert _segment_work_day_counts("115000003", 20) == [10, 10]
    assert _segment_work_day_counts("115000004", 25) == [12, 13]
    assert _segment_work_day_counts("115000008", 30) == [10, 10, 10]
    assert _segment_work_day_counts("115000009", 30) == [10, 10, 10]
    assert _segment_work_day_counts("115000020", 25) == [25]


def test_segment_schedule_and_money_proration_are_gapless_and_exact():
    first_rows, first_end = _schedule_rows_for_segment(
        date(2026, 6, 1), 10, "週休2日"
    )
    second_rows, second_end = _schedule_rows_for_segment(
        first_end + timedelta(days=1),
        10,
        "週休2日",
    )

    assert sum(is_work_day for _, is_work_day in first_rows) == 10
    assert sum(is_work_day for _, is_work_day in second_rows) == 10
    assert second_rows[0][0] == first_end + timedelta(days=1)
    assert second_end > first_end
    assert _prorate_amount(1000, [10, 10, 10]) == [
        Decimal("333.33"), Decimal("333.33"), Decimal("333.34")
    ]


def test_finance_duplicate_fixture_changes_source_location_not_fingerprint():
    first = _finance_duplicate_normalized_result(
        date(2026, 7, 22), "fixture_a.xlsx", 17
    )["normalized_rows"][0]
    second = _finance_duplicate_normalized_result(
        date(2026, 7, 22), "fixture_b.xlsx", 23
    )["normalized_rows"][0]

    assert first["source_file"] != second["source_file"]
    assert first["source_row"] != second["source_row"]
    assert build_dedup_fingerprint(first) == build_dedup_fingerprint(second)
