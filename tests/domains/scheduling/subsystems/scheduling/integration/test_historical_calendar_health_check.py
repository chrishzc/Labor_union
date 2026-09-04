from __future__ import annotations

from copy import deepcopy
from datetime import date

from openpyxl import Workbook

from scripts.diagnostics.historical_calendar_health_check import (
    MISSING_COMPLETED_ASSIGNMENT,
    MISSING_DATES,
    MISSING_STAFF,
    SHOULD_NOT_DISPLAY,
    VISIBLE,
    historical_calendar_health_check,
)


class _FakeCursor:
    def __init__(self, state):
        self.state = state
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=()):
        sql = " ".join(statement.split())
        if not sql.upper().startswith("SELECT"):
            self.state["writes"].append((sql, params))
            raise AssertionError(f"health check attempted a write: {sql}")

        if "SELECT id,name FROM staff WHERE name=%s" in sql:
            self.rows = (
                [{"id": 7, "name": "Alice"}]
                if params == ("Alice",)
                else []
            )
        elif "FROM case_staff_assignments WHERE case_no=%s" in sql:
            case_no = params[0]
            self.rows = {
                "1001": [
                    {
                        "id": 501,
                        "assigned_start_date": date(2025, 10, 1),
                        "assigned_end_date": date(2025, 10, 3),
                    }
                ],
                "1006": [
                    {
                        "id": 506,
                        "assigned_start_date": date(2025, 10, 1),
                        "assigned_end_date": date(2025, 10, 3),
                    }
                ],
            }.get(case_no, [])
        elif "SELECT 1 AS staff_exists FROM staff WHERE id = %s" in sql:
            self.rows = [{"staff_exists": 1}] if params == (7,) else []
        elif "FROM staff_schedule ss" in sql:
            self.rows = []
        elif "csa.status='completed'" in sql and "orders_historical_precision_restart" in sql:
            self.rows = [
                {
                    "assignment_id": 501,
                    "case_no": "1001",
                    "staff_id": 7,
                    "assigned_start_date": date(2025, 10, 1),
                    "assigned_end_date": date(2025, 10, 3),
                    "client_name": "Client A",
                    "order_status": "歷史服務完成",
                    "staff_name": "Alice",
                }
            ]
        elif "FROM caregiver_availability_lock_days d" in sql:
            self.rows = []
        elif "COALESCE(o.actual_start_date, csa.assigned_start_date)" in sql:
            self.rows = []
        elif "FROM scheduling_staff_unavailability_blocks" in sql:
            self.rows = []
        else:
            raise AssertionError(f"unexpected read query: {sql}")
        return len(self.rows)

    def fetchone(self):
        return None if not self.rows else self.rows[0]

    def fetchall(self):
        return list(self.rows)


class _FakeConnection:
    def __init__(self, state):
        self.state = state

    def cursor(self):
        return _FakeCursor(self.state)

    def close(self):
        pass


class _ConnectionFactory:
    def __init__(self, state):
        self.state = state

    def __call__(self):
        return _FakeConnection(self.state)


def _write_workbook(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "historical"
    sheet.append(["client_name", "case_no", "start_date", "end_date", "status", "staff_name"])
    sheet.append(["Client A", "1001", date(2025, 10, 1), date(2025, 10, 3), 1, "Alice"])
    sheet.append(["Client B", "1002", date(2025, 10, 1), date(2025, 10, 3), 1, None])
    sheet.append(["Client C", "1003", None, None, 1, "Alice"])
    sheet.append(["Client D", "1004", date(2025, 10, 1), date(2025, 10, 3), 1, "Alice"])
    sheet.append(["Client E", "1005", date(2025, 10, 1), date(2025, 10, 3), 0, "Alice"])
    sheet.append(["Client F", "1006", date(2025, 10, 1), date(2025, 10, 3), 1, "Alice"])
    workbook.save(path)


def test_health_check_reuses_current_monthly_semantics_and_never_writes(tmp_path):
    workbook_path = tmp_path / "historical.xlsx"
    _write_workbook(workbook_path)
    state = {
        "writes": [],
        "root_rows": {
            "orders": (("1001", "歷史服務完成"), ("1006", "歷史服務完成")),
            "assignments": ((501, "1001", "completed"), (506, "1006", "completed")),
            "schedule": (),
        },
    }
    before = deepcopy(state["root_rows"])

    result = historical_calendar_health_check(
        workbook_path,
        connection_factory=_ConnectionFactory(state),
    )

    assert result["classification_counts"] == {
        VISIBLE: 1,
        MISSING_STAFF: 1,
        MISSING_DATES: 1,
        MISSING_COMPLETED_ASSIGNMENT: 1,
        SHOULD_NOT_DISPLAY: 2,
    }
    classifications = {
        row["case_no"]: (row["classification"], row["reason"])
        for row in result["rows"]
    }
    assert classifications["1001"] == (VISIBLE, "current_monthly_projection_visible")
    assert classifications["1002"] == (MISSING_STAFF, "source_staff_missing")
    assert classifications["1003"] == (MISSING_DATES, "source_service_interval_invalid")
    assert classifications["1004"] == (
        MISSING_COMPLETED_ASSIGNMENT,
        "completed_assignment_missing",
    )
    assert classifications["1005"] == (SHOULD_NOT_DISPLAY, "source_status_not_deposit_paid")
    assert classifications["1006"] == (
        SHOULD_NOT_DISPLAY,
        "current_monthly_semantics_exclude_historical_assignment",
    )
    assert state["writes"] == []
    assert state["root_rows"] == before
