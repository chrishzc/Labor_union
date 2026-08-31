"""Regression coverage for selected-week subsidy completion rows."""

from datetime import date

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


def _source(case_no: str, completion: date, identity_status: str = "一般市民") -> dict:
    return {
        "case_no": case_no,
        "identity_status": identity_status,
        "actual_start_date": date(2026, 7, 1),
        "actual_end_date": completion,
        "service_days": 20,
        "service_hours_per_day": 8,
        "employer_name": "測試案家",
        "employer_address": "測試地址",
        "staff_name": "測試人員",
        "survey_details": {},
    }


def test_completion_period_includes_boundaries_and_excludes_other_weeks():
    connection = _Connection([
        _source("BEFORE", date(2026, 8, 16)),
        _source("WEEK-END", date(2026, 8, 23), "補助市民"),
        _source("WEEK-START", date(2026, 8, 17)),
        _source("AFTER", date(2026, 8, 24)),
    ])

    result = register.build_completion_period_subsidy_rows(
        date(2026, 8, 17),
        date(2026, 8, 23),
        lambda: connection,
    )

    assert [row["市府訂單號碼"] for row in result["general_citizen_rows"]] == ["WEEK-START"]
    assert [row["市府訂單號碼"] for row in result["subsidized_citizen_rows"]] == ["WEEK-END"]
    assert result["general_citizen_rows"][0]["序號"] == 1
    assert result["subsidized_citizen_rows"][0]["序號"] == 1
    assert connection.closed is True
    assert "INSERT" not in connection.cursor_instance.executed[0][0].upper()


def test_invalid_completion_period_is_rejected_before_database_access():
    with pytest.raises(ValueError, match="period_start"):
        register.build_completion_period_subsidy_rows(
            date(2026, 8, 24),
            date(2026, 8, 23),
            lambda: (_ for _ in ()).throw(AssertionError("database must not be opened")),
        )
