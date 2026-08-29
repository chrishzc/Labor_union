"""
File: test_government_subsidy_repository_guards.py
Description: 驗證政府溢撥 repository 的收款帳戶與 projection lineage fail-closed 邊界。
"""

from datetime import date, datetime, timezone

import pytest

from infrastructure.mysql.government_subsidy_repository import (
    MySqlGovernmentSubsidyRepository,
    _overpayment_outbox_lineage,
)
from shared_kernel.clock import FixedBusinessClock


class _Cursor:
    def __init__(self, rows=(), lineage=None):
        self.rows = rows
        self.lineage = lineage
        self.statement = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _params=()):
        self.statement = statement

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.lineage


class _Connection:
    def __init__(self, rows=(), lineage=None):
        self.cursor_value = _Cursor(rows, lineage)

    def cursor(self):
        return self.cursor_value


@pytest.mark.parametrize(
    ("rows", "error"),
    [
        (
            (
                {
                    "bank_code": "004",
                    "account_number": "123456789012",
                    "account_name": "新竹市政府",
                    "effective_from": date(2026, 1, 1),
                },
                {
                    "bank_code": "005",
                    "account_number": "987654321098",
                    "account_name": "新竹市政府",
                    "effective_from": date(2026, 2, 1),
                },
            ),
            "government_subsidy_recipient_account_ambiguous",
        ),
        (
            (
                {
                    "bank_code": "004",
                    "account_number": "123456789012",
                    "account_name": "新竹市政府",
                    "effective_from": date(2026, 10, 1),
                },
            ),
            "government_subsidy_recipient_account_invalid",
        ),
        (
            (
                {
                    "bank_code": "004",
                    "account_number": "",
                    "account_name": "新竹市政府",
                    "effective_from": date(2026, 1, 1),
                },
            ),
            "government_subsidy_recipient_account_invalid",
        ),
    ],
)
def test_return_recipient_never_selects_ambiguous_future_or_unusable_account(
    rows, error
):
    connection = _Connection(rows)

    with pytest.raises(ValueError, match=error):
        MySqlGovernmentSubsidyRepository(
            connection,
            FixedBusinessClock(datetime(2026, 8, 27, tzinfo=timezone.utc)),
        ).load_return_recipient(
            "2026-09-01", "evidence-1", lock=False
        )

    assert "LIMIT 1" not in connection.cursor_value.statement.upper()


def test_apply_rejects_future_recipient_even_when_due_date_is_later():
    connection = _Connection(
        (
            {
                "bank_code": "004",
                "account_number": "123456789012",
                "account_name": "新竹市政府",
                "effective_from": date(2026, 8, 28),
            },
        )
    )

    with pytest.raises(
        ValueError, match="government_subsidy_recipient_account_invalid"
    ):
        MySqlGovernmentSubsidyRepository(
            connection,
            FixedBusinessClock(datetime(2026, 8, 27, tzinfo=timezone.utc)),
        ).load_return_recipient("2026-12-31", "evidence-1", lock=False)


def test_apply_accepts_recipient_effective_on_business_clock_date():
    connection = _Connection(
        (
            {
                "bank_code": "004",
                "account_number": "123456789012",
                "account_name": "新竹市政府",
                "effective_from": date(2026, 8, 27),
            },
        )
    )

    recipient = MySqlGovernmentSubsidyRepository(
        connection,
        FixedBusinessClock(datetime(2026, 8, 27, tzinfo=timezone.utc)),
    ).load_return_recipient("2026-12-31", "evidence-1", lock=False)

    assert recipient.effective_date == "2026-08-27"


class _QueryCursor:
    def __init__(self, recipient_row):
        self.recipient_row = recipient_row
        self.result = None
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _params=()):
        self.statements.append(statement)
        if "FROM government_subsidy_overpayments" in statement:
            self.result = {
                "overpayment_identity": "over-1",
                "source_finance_import_row_id": 11,
                "source_transaction_id": 21,
                "payer_identity": "hccg",
                "remaining_amount_ntd": 700,
                "status": "pending_review",
                "projection_version": 3,
            }
        elif "FROM subsidy_claim_batch_items" in statement:
            self.result = []
        elif "FROM government_payer_receiving_accounts" in statement:
            self.result = [self.recipient_row]

    def fetchone(self):
        return self.result if isinstance(self.result, dict) else None

    def fetchall(self):
        return self.result if isinstance(self.result, list) else []


class _QueryConnection:
    def __init__(self, recipient_row):
        self.cursor_value = _QueryCursor(recipient_row)

    def cursor(self):
        return self.cursor_value


def test_query_rejects_future_recipient_using_business_clock_not_due_date():
    connection = _QueryConnection(
        {
            "bank_code": "004",
            "account_number": "123456789012",
            "account_name": "新竹市政府",
            "effective_from": date(2026, 8, 28),
        }
    )

    result = MySqlGovernmentSubsidyRepository(
        connection,
        FixedBusinessClock(datetime(2026, 8, 27, tzinfo=timezone.utc)),
    ).query_overpayment("over-1")

    assert result.return_recipient.ready is False
    assert result.return_recipient.blockers == (
        "government_subsidy_recipient_account_invalid",
    )
    assert result.available_actions == ()


def test_query_accepts_recipient_effective_on_business_clock_date():
    connection = _QueryConnection(
        {
            "bank_code": "004",
            "account_number": "123456789012",
            "account_name": "新竹市政府",
            "effective_from": date(2026, 8, 27),
        }
    )

    result = MySqlGovernmentSubsidyRepository(
        connection,
        FixedBusinessClock(datetime(2026, 8, 27, tzinfo=timezone.utc)),
    ).query_overpayment("over-1")

    assert result.return_recipient.ready is True
    assert result.available_actions == ("return",)


def test_overpayment_lineage_requires_projection_for_source_transaction():
    connection = _Connection(
        lineage={"claim_batch_id": 4, "transaction_id": 9, "projection_event_id": 11}
    )

    assert _overpayment_outbox_lineage(connection.cursor_value, "over-1") == (4, 9, 11)
    statement = " ".join(connection.cursor_value.statement.split()).lower()
    assert "event.transaction_id=transaction.id" in statement
