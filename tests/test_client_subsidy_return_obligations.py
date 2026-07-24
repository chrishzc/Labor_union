from datetime import date
import sqlite3

import pytest

import services.client_subsidy_return_obligations as obligation_service
from services.client_subsidy_return_obligations import (
    activate_subsidy_return_obligation,
    calculate_subsidy_return_due_date,
)


@pytest.fixture(autouse=True)
def accounting_source_projection(monkeypatch):
    calls = []

    def load_with_cursor(cursor, case_no):
        calls.append((cursor, case_no))
        return {"client": {"identity_status": "一般市民"}}

    monkeypatch.setattr(
        obligation_service,
        "load_case_accounting_source_with_cursor",
        load_with_cursor,
    )
    return calls


def test_calculate_subsidy_return_due_date_month_end_plus_five_days():
    # 2026-07-15 -> Month end 2026-07-31 -> + 5 days = 2026-08-05
    assert calculate_subsidy_return_due_date("2026-07-15") == "2026-08-05"
    # 2026-02-10 -> Month end 2026-02-28 -> + 5 days = 2026-03-05
    assert calculate_subsidy_return_due_date("2026-02-10") == "2026-03-05"
    # Year-end rollover: 2026-12-01 -> Month end 2026-12-31 -> + 5 days = 2027-01-05
    assert calculate_subsidy_return_due_date(date(2026, 12, 1)) == "2027-01-05"
    assert calculate_subsidy_return_due_date(None) is None
    assert calculate_subsidy_return_due_date("") is None


class MySQLCursorDouble:
    __module__ = "mysql.connector.cursor"

    def __init__(self, selected_row):
        self.selected_row = selected_row
        self.statements = []

    def execute(self, sql, params):
        self.statements.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.selected_row


@pytest.fixture
def cursor():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE client_payments (
            id INTEGER PRIMARY KEY,
            case_no TEXT NOT NULL,
            amount_receivable INTEGER NOT NULL,
            amount_received INTEGER NOT NULL,
            subsidy_return_receivable INTEGER,
            subsidy_return_refunded INTEGER,
            subsidy_return_due_date TEXT,
            subsidy_refund_receivable INTEGER,
            subsidy_refund_due_date TEXT
        )
        """
    )
    yield connection.cursor()
    connection.close()


def insert_payment(cursor, *, receivable=10_000, received=10_000, **canonical):
    cursor.execute(
        """
        INSERT INTO client_payments (
            id, case_no, amount_receivable, amount_received,
            subsidy_return_receivable, subsidy_return_refunded,
            subsidy_return_due_date,
            subsidy_refund_receivable, subsidy_refund_due_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 777, 'legacy-date')
        """,
        (
            1,
            "CASE-1",
            receivable,
            received,
            canonical.get("return_receivable"),
            canonical.get("refunded"),
            canonical.get("due_date"),
        ),
    )


@pytest.mark.parametrize("received", [9_999, 10_001])
def test_underpayment_and_overpayment_do_not_activate(cursor, received):
    insert_payment(cursor, received=received)

    result = activate_subsidy_return_obligation(cursor, 1, 2_000, "2026-08-31")

    assert result == {"obligation": None, "result": "review_required"}
    assert cursor.execute(
        "SELECT subsidy_return_receivable FROM client_payments WHERE id = 1"
    ).fetchone()[0] is None


def test_exact_full_receipt_activates_canonical_fields_only(cursor):
    insert_payment(cursor)

    result = activate_subsidy_return_obligation(cursor, 1, 2_000, date(2026, 8, 31))

    assert result == {
        "obligation": {
            "subsidy_return_receivable": 2_000,
            "subsidy_return_refunded": 0,
            "due_date": "2026-08-31",
            "remaining": 2_000,
        },
        "result": "activated",
    }
    assert cursor.execute(
        """
        SELECT subsidy_return_receivable, subsidy_return_refunded,
               subsidy_return_due_date,
               subsidy_refund_receivable, subsidy_refund_due_date
        FROM client_payments WHERE id = 1
        """
    ).fetchone() == (2_000, 0, "2026-08-31", 777, "legacy-date")


def test_none_due_date_is_persisted_as_null_without_inference(cursor):
    insert_payment(cursor)

    result = activate_subsidy_return_obligation(cursor, 1, 2_000, None)

    assert result["result"] == "activated"
    assert result["obligation"]["due_date"] is None
    assert cursor.execute(
        "SELECT subsidy_return_due_date FROM client_payments WHERE id = 1"
    ).fetchone()[0] is None


def test_matching_existing_obligation_is_idempotent(cursor):
    insert_payment(
        cursor,
        return_receivable=2_000,
        refunded=500,
        due_date="2026-08-31",
    )

    result = activate_subsidy_return_obligation(cursor, 1, 2_000, "2026-08-31")

    assert result == {
        "obligation": {
            "subsidy_return_receivable": 2_000,
            "subsidy_return_refunded": 500,
            "due_date": "2026-08-31",
            "remaining": 1_500,
        },
        "result": "existing",
    }


@pytest.mark.parametrize(
    ("return_amount", "due_date"),
    [(2_001, "2026-08-31"), (2_000, "2026-09-01")],
)
def test_existing_amount_or_due_date_conflict_requires_review(
    cursor, return_amount, due_date
):
    insert_payment(
        cursor,
        return_receivable=2_000,
        refunded=500,
        due_date="2026-08-31",
    )

    result = activate_subsidy_return_obligation(cursor, 1, return_amount, due_date)

    assert result["result"] == "review_required"
    assert cursor.execute(
        "SELECT subsidy_return_receivable, subsidy_return_due_date "
        "FROM client_payments WHERE id = 1"
    ).fetchone() == (2_000, "2026-08-31")


def test_mysql_locks_payment_before_activating_obligation():
    cursor = MySQLCursorDouble(("CASE-1", 10_000, 10_000, None, None, None))

    result = activate_subsidy_return_obligation(
        cursor, 1, 2_000, "2026-08-31"
    )

    assert result["result"] == "activated"
    assert cursor.statements[0] == (
        "SELECT case_no, amount_receivable, amount_received, "
        "subsidy_return_receivable, subsidy_return_refunded, "
        "subsidy_return_due_date FROM client_payments "
        "WHERE id = %s FOR UPDATE",
        (1,),
    )
    assert cursor.statements[1][0].startswith("UPDATE client_payments SET ")


def test_second_mysql_worker_reviews_conflicting_locked_content_without_update():
    # A concurrent worker must lock and re-read the row.  If the first worker
    # activated different terms, the second one reviews them without writing.
    cursor = MySQLCursorDouble(
        ("CASE-1", 10_000, 10_000, 2_000, 0, "2026-08-31")
    )

    result = activate_subsidy_return_obligation(
        cursor, 1, 2_001, "2026-09-01"
    )

    assert result["result"] == "review_required"
    assert len(cursor.statements) == 1
    assert cursor.statements[0][0].endswith("WHERE id = %s FOR UPDATE")


def test_sqlite_query_remains_compatible_without_for_update(cursor):
    insert_payment(cursor)

    result = activate_subsidy_return_obligation(cursor, 1, 2_000, None)

    assert result["result"] == "activated"


def test_non_positive_return_amount_does_not_activate(cursor):
    insert_payment(cursor)

    result = activate_subsidy_return_obligation(cursor, 1, 0, None)

    assert result["result"] == "review_required"


def test_missing_payment_requires_review(cursor):
    result = activate_subsidy_return_obligation(cursor, 99, 2_000, None)

    assert result == {"obligation": None, "result": "review_required"}


def test_blank_due_date_is_rejected_instead_of_guessed(cursor):
    insert_payment(cursor)

    with pytest.raises(ValueError):
        activate_subsidy_return_obligation(cursor, 1, 2_000, "")


def test_service_projects_identity_with_same_cursor_and_payment_case_no(
    cursor, accounting_source_projection
):
    insert_payment(cursor)

    result = activate_subsidy_return_obligation(cursor, 1, 2_000, None)

    assert result["result"] == "activated"
    assert accounting_source_projection == [(cursor, "CASE-1")]


def test_unsupported_projected_identity_requires_review_without_update(
    cursor, monkeypatch
):
    insert_payment(cursor)
    monkeypatch.setattr(
        obligation_service,
        "load_case_accounting_source_with_cursor",
        lambda active_cursor, case_no: {
            "client": {"identity_status": "低收入戶"}
        },
    )

    result = activate_subsidy_return_obligation(cursor, 1, 2_000, None)

    assert result == {"obligation": None, "result": "review_required"}
    assert cursor.execute(
        "SELECT subsidy_return_receivable FROM client_payments WHERE id = 1"
    ).fetchone()[0] is None


def test_projection_error_propagates_instead_of_being_swallowed(cursor, monkeypatch):
    insert_payment(cursor)

    def fail_projection(active_cursor, case_no):
        raise RuntimeError("projection failed")

    monkeypatch.setattr(
        obligation_service,
        "load_case_accounting_source_with_cursor",
        fail_projection,
    )

    with pytest.raises(RuntimeError, match="projection failed"):
        activate_subsidy_return_obligation(cursor, 1, 2_000, None)
