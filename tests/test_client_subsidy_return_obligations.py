from datetime import date
import sqlite3

import pytest

from services.client_subsidy_return_obligations import (
    activate_subsidy_return_obligation,
)


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
            id, amount_receivable, amount_received,
            subsidy_return_receivable, subsidy_return_refunded,
            subsidy_return_due_date,
            subsidy_refund_receivable, subsidy_refund_due_date
        ) VALUES (?, ?, ?, ?, ?, ?, 777, 'legacy-date')
        """,
        (
            1,
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
    cursor = MySQLCursorDouble((10_000, 10_000, None, None, None))

    result = activate_subsidy_return_obligation(
        cursor, 1, 2_000, "2026-08-31"
    )

    assert result["result"] == "activated"
    assert cursor.statements[0] == (
        "SELECT amount_receivable, amount_received, "
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
        (10_000, 10_000, 2_000, 0, "2026-08-31")
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
