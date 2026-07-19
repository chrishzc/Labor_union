import sqlite3

import pytest

from services.client_payment_snapshots import create_client_payment_snapshot


PLAN = {
    "stages": [
        {"stage": "deposit", "receivable": 3_000, "due_date": "2026-07-01"},
        {"stage": "first_payment", "receivable": 4_000, "due_date": "2026-07-15"},
        {"stage": "second_payment", "receivable": 5_000, "due_date": None},
    ],
    "amount_receivable": 12_000,
    "client_prepaid_subsidy_amount": 2_000,
    "subsidy_return_amount": 2_000,
}


@pytest.fixture
def cursor():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE client_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_no TEXT NOT NULL UNIQUE,
            deposit_receivable INTEGER NOT NULL,
            deposit_due_date TEXT,
            first_payment_receivable INTEGER NOT NULL,
            first_payment_due_date TEXT,
            second_payment_receivable INTEGER NOT NULL,
            second_payment_due_date TEXT,
            amount_receivable INTEGER NOT NULL
        )
        """
    )
    yield connection.cursor()
    connection.close()


def order(**changes):
    value = {
        "case_no": "CASE-001",
        "service_days": 36,
        "service_hours_per_day": 9,
        "subsidy_eligibility": "一般市民",
        "client_floor_fee": 0,
        "start_date": "2026-07-15",
    }
    value.update(changes)
    return value


def schedule(**changes):
    value = {"deposit_service_days": 5, "deposit_due_date": "2026-07-01"}
    value.update(changes)
    return value


def calculator(plan=PLAN, captured=None):
    def calculate(calculator_order, collection_schedule):
        assert collection_schedule["deposit_service_days"] == 5
        if captured is not None:
            captured.update(calculator_order)
        return {"client_ledger_plan": dict(plan)}

    return calculate


def test_maps_real_calculator_plan_to_formal_schema(cursor):
    result = create_client_payment_snapshot(cursor, order(), schedule())

    assert result["result"] == "created"
    assert result["plan"]["stages"][0]["stage"] == "deposit"
    stored = cursor.execute(
        """SELECT deposit_receivable, first_payment_receivable,
                  second_payment_receivable, amount_receivable
           FROM client_payments WHERE case_no=?""",
        ("CASE-001",),
    ).fetchone()
    assert stored == (13_500, 40_500, 43_200, 97_200)


def test_subsidy_plan_is_returned_but_never_persisted(cursor):
    result = create_client_payment_snapshot(
        cursor, order(bank_received_amount=999_999), schedule(), calculator=calculator()
    )

    assert result == {"payment_id": 1, "plan": PLAN, "result": "created"}
    columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(client_payments)").fetchall()
    }
    assert "stages" not in columns
    assert "subsidy_return_amount" not in columns
    assert cursor.execute(
        "SELECT amount_receivable FROM client_payments WHERE case_no=?",
        ("CASE-001",),
    ).fetchone() == (12_000,)


def test_actual_start_date_precedes_start_date(cursor):
    captured = {}
    create_client_payment_snapshot(
        cursor,
        order(start_date="2026-07-15", actual_start_date="2026-07-20"),
        schedule(),
        calculator=calculator(captured=captured),
    )

    assert captured["service_start_date"] == "2026-07-20"


def test_same_existing_snapshot_is_idempotent(cursor):
    first = create_client_payment_snapshot(
        cursor, order(), schedule(), calculator=calculator()
    )
    second = create_client_payment_snapshot(
        cursor, order(), schedule(), calculator=calculator()
    )

    assert first["payment_id"] == second["payment_id"]
    assert second["result"] == "existing"
    assert cursor.execute("SELECT COUNT(*) FROM client_payments").fetchone()[0] == 1


@pytest.mark.parametrize(
    ("stage_name", "field", "changed_value"),
    [
        ("deposit", "receivable", 3_001),
        ("first_payment", "due_date", "2026-07-16"),
        ("second_payment", "receivable", 5_001),
    ],
)
def test_any_existing_stage_difference_requires_review(
    cursor, stage_name, field, changed_value
):
    create_client_payment_snapshot(cursor, order(), schedule(), calculator=calculator())
    changed = {**PLAN, "stages": [dict(stage) for stage in PLAN["stages"]]}
    next(stage for stage in changed["stages"] if stage["stage"] == stage_name)[field] = changed_value

    result = create_client_payment_snapshot(
        cursor, order(bank_received_amount=changed_value), schedule(), calculator=calculator(changed)
    )

    assert result["result"] == "review_required"
    assert cursor.execute(
        "SELECT deposit_receivable FROM client_payments WHERE case_no=?", ("CASE-001",)
    ).fetchone() == (3_000,)


def test_subsidy_output_difference_does_not_mutate_snapshot(cursor):
    create_client_payment_snapshot(cursor, order(), schedule(), calculator=calculator())
    changed = {**PLAN, "subsidy_return_amount": 9_999}

    result = create_client_payment_snapshot(
        cursor, order(), schedule(), calculator=calculator(changed)
    )

    assert result["result"] == "existing"
    assert result["plan"]["subsidy_return_amount"] == 9_999


@pytest.mark.parametrize(
    ("order_changes", "schedule_changes", "reason"),
    [
        ({"start_date": None}, {}, "service_start_date_missing"),
        ({}, {"deposit_service_days": None}, "deposit_service_days_missing"),
        ({}, {"deposit_due_date": None}, "deposit_due_date_missing"),
    ],
)
def test_missing_required_terms_require_review_without_insert(
    cursor, order_changes, schedule_changes, reason
):
    called = False

    def should_not_run(_order, _schedule):
        nonlocal called
        called = True

    result = create_client_payment_snapshot(
        cursor,
        order(**order_changes),
        schedule(**schedule_changes),
        calculator=should_not_run,
    )

    assert result == {
        "payment_id": None,
        "plan": None,
        "result": "review_required",
        "reason": reason,
    }
    assert called is False
    assert cursor.execute("SELECT COUNT(*) FROM client_payments").fetchone()[0] == 0


def test_rejects_malformed_stage_plan(cursor):
    malformed = {**PLAN, "stages": PLAN["stages"][:2]}
    with pytest.raises(ValueError, match="all three"):
        create_client_payment_snapshot(
            cursor, order(), schedule(), calculator=calculator(malformed)
        )


def test_requires_case_number_before_calculation(cursor):
    with pytest.raises(ValueError, match="case_no"):
        create_client_payment_snapshot(
            cursor, order(case_no=""), schedule(), calculator=calculator()
        )
