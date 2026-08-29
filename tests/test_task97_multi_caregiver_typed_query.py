"""Task 97 focused checks for typed Scheduling read boundaries."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from infrastructure.mysql.multi_caregiver_schedule_query_repository import (
    MySqlMultiCaregiverScheduleQueryRepository,
)
from subsystems.scheduling.multi_caregiver_schedule_query import (
    CaseAssignmentQuery,
    MultiCaregiverScheduleQueryApplication,
)


ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, results):
        self._results = iter(results)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return next(self._results)

    def fetchall(self):
        return next(self._results)


class _Connection:
    def __init__(self, results):
        self.cursor_obj = _Cursor(results)
        self.closed = False

    def cursor(self):
        return self.cursor_obj


def _assignment_row():
    return {
        "id": 21,
        "case_no": "115000001",
        "staff_id": 31,
        "status": "active",
        "assigned_start_date": date(2026, 8, 1),
        "assigned_end_date": date(2026, 8, 10),
        "planned_hours": Decimal("100"),
        "actual_hours": Decimal("20"),
        "service_hours_per_day": Decimal("10"),
        "staff_name": "測試月嫂",
        "client_name": "測試客戶",
    }


def test_assignment_schedule_adapter_borrows_connection_and_returns_typed_result():
    connection = _Connection([
        {"current_date": date(2026, 8, 29)},
        _assignment_row(),
        {"id": 1},
        None,
        [{
            "id": 7,
            "case_no": "115000001",
            "staff_id": 31,
            "assignment_id": 21,
            "work_date": date(2026, 8, 1),
            "is_work_day": 1,
            "is_double_pay": 0,
            "notes": None,
        }],
    ])

    result = MySqlMultiCaregiverScheduleQueryRepository(connection).get_assignment_schedule(21)

    assert result.assignment.id == 21
    assert result.schedule_days[0].assignment_id == 21
    assert result.schedule_days[0].is_historical is True
    assert connection.closed is False
    assert all("SELECT *" not in sql.upper() for sql, _ in connection.cursor_obj.executed)
    assert all("COMMIT" not in sql.upper() and "ROLLBACK" not in sql.upper() for sql, _ in connection.cursor_obj.executed)


def test_case_query_is_scheduling_owned_and_derives_summary_from_typed_rows():
    class Repository:
        def list_case_assignments(self, case_no):
            assert case_no == "115000001"
            return ()

        def list_staff_assignments(self, staff_id):
            return ()

        def get_assignment_schedule(self, assignment_id):
            raise AssertionError("not used")

    result = MultiCaregiverScheduleQueryApplication(Repository()).list_case_assignments(" 115000001 ")

    assert isinstance(result, CaseAssignmentQuery)
    assert result.assignments == ()
    assert result.summary is None


def test_case_assignment_adapter_preserves_zero_defaults_for_nullable_legacy_counts():
    row = {
        **_assignment_row(),
        "original_assigned_start_date": None,
        "original_assigned_end_date": None,
        "planned_hours": None,
        "actual_hours": None,
        "service_days": None,
        "actual_service_days": None,
        "rest_days": None,
        "substitute_service_days": None,
        "deferred_leave_days": None,
        "leave_resolution_days": None,
    }
    connection = _Connection([[row]])

    result = MySqlMultiCaregiverScheduleQueryRepository(
        connection
    ).list_case_assignments("115000001")

    assert result[0].planned_hours == Decimal("0")
    assert result[0].actual_hours == Decimal("0")
    assert result[0].service_days == 0
    assert result[0].actual_service_days == 0


def test_task97_routes_are_typed_and_do_not_own_database_access():
    for relative_path in (
        "api/routes/multi_caregiver_schedule_read.py",
        "api/routes/multi_caregiver_case_assignments.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "response_model=BaseResponse[dict" not in source
        assert "response_model=BaseResponse[List[Dict" not in source
        assert "get_connection" not in source
        assert "cursor.execute" not in source
        assert ".commit(" not in source
        assert ".rollback(" not in source
