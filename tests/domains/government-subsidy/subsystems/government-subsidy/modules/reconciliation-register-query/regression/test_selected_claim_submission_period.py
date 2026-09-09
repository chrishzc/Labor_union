"""Regression coverage for subsidy rows selected by formal claim submission date."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from subsystems.government_subsidy import reconciliation_register_query as register


class _Cursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        self.executed.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def _source(case_no: str, submitted_at: datetime, identity_status: str = "一般市民") -> dict:
    return {
        "case_no": case_no,
        "identity_status": identity_status,
        "actual_start_date": date(2026, 7, 1),
        "actual_end_date": date(2027, 1, 15),
        "service_days": 20,
        "service_hours_per_day": 8,
        "employer_name": "測試案家",
        "employer_address": "測試地址",
        "staff_name": "測試人員",
        "survey_details": {},
        "claimed_hours": Decimal("40"),
        "unit_price": Decimal("300"),
        "requested_amount": Decimal("12000"),
        "application_year": 2026,
        "quarter": 4,
        "claim_status": "submitted",
        "claim_submitted_at": submitted_at,
    }


def test_claim_submission_period_uses_formal_batch_date_not_service_end():
    connection = _Connection([
        _source("114000007", datetime(2026, 12, 31, 16, 30)),
    ])

    result = register.build_claim_submission_period_subsidy_rows(
        date(2026, 1, 1),
        date(2026, 12, 31),
        lambda: connection,
    )

    assert [row["市府訂單號碼"] for row in result["general_citizen_rows"]] == ["114000007"]
    row = result["general_citizen_rows"][0]
    assert row["服務結束"] == date(2027, 1, 15)
    assert row["核銷月份"] == "2026-12"
    assert row["補助時數"] == Decimal("40")
    assert row["補助款金額"] == Decimal("12000")
    assert result["general_citizen_rows"][0]["序號"] == 1
    assert result["subsidized_citizen_rows"] == []
    assert connection.closed is True
    sql, params = connection.cursor_instance.executed[0]
    assert "subsidy_claim_batch_items" in sql
    assert "batch.submitted_at >= %s" in sql
    assert "batch.submitted_at < %s" in sql
    assert date(2026, 1, 1) in params
    assert date(2027, 1, 1) in params
    assert "INSERT" not in sql.upper()


def test_invalid_claim_submission_period_is_rejected_before_database_access():
    with pytest.raises(ValueError, match="period_start"):
        register.build_claim_submission_period_subsidy_rows(
            date(2026, 8, 24),
            date(2026, 8, 23),
            lambda: (_ for _ in ()).throw(AssertionError("database must not be opened")),
        )
