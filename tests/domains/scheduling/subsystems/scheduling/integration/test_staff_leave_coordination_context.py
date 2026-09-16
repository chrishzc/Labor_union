from datetime import date

import pytest

from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.connection.calls.append((sql, params))

    def fetchone(self):
        return self.connection.request_row

    def fetchall(self):
        return self.connection.target_rows


class _Connection:
    def __init__(self, request_row, target_rows=()):
        self.request_row = request_row
        self.target_rows = target_rows
        self.calls = []

    def cursor(self):
        return _Cursor(self)


def _request_row(*, status="accepted_for_processing", version=3):
    return {
        "id": 17,
        "staff_id": 9,
        "line_user_id": "Ustaff",
        "leave_start_date": date(2026, 9, 20),
        "leave_end_date": date(2026, 9, 22),
        "request_reason": "leave",
        "request_status": status,
        "aggregate_version": version,
        "request_fingerprint": "fp",
    }


def test_coordination_context_projects_current_case_and_customer_recipient():
    connection = _Connection(
        _request_row(),
        (
            {"case_no": "CASE-001", "client_line_user_id": " Uclient "},
            {"case_no": "CASE-002", "client_line_user_id": None},
        ),
    )

    result = MySqlStaffLeaveIntakeRepository(connection).coordination_context(17, 3)

    assert result == {
        "request_id": 17,
        "request_version": 3,
        "leave_start_date": date(2026, 9, 20),
        "leave_end_date": date(2026, 9, 22),
        "targets": [
            {"case_no": "CASE-001", "client_line_user_id": "Uclient"},
            {"case_no": "CASE-002", "client_line_user_id": None},
        ],
    }
    target_sql, target_args = connection.calls[-1]
    assert "case_staff_assignments" in target_sql
    assert "g.effective_generation_id" in target_sql
    assert target_args == (9, date(2026, 9, 22), date(2026, 9, 20))


def test_coordination_context_rejects_stale_leave_version_before_case_projection():
    connection = _Connection(_request_row(version=4))

    with pytest.raises(ValueError, match="leave_request_stale"):
        MySqlStaffLeaveIntakeRepository(connection).coordination_context(17, 3)

    assert len(connection.calls) == 1


def test_coordination_context_requires_union_accepted_leave():
    connection = _Connection(_request_row(status="pending"))

    with pytest.raises(ValueError, match="leave_request_not_accepted"):
        MySqlStaffLeaveIntakeRepository(connection).coordination_context(17, 3)

    assert len(connection.calls) == 1
