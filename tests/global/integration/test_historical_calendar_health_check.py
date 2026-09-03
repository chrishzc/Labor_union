"""Focused orchestration coverage for the read-only historical calendar health check."""

from datetime import date
from pathlib import Path

from openpyxl import Workbook

from scripts.historical_calendar_health_check import run_historical_calendar_health_check


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.current = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.connection.executed.append((normalized, params))
        assert normalized.upper().startswith("SELECT ")
        if "FROM order_lifecycle_state_events" in normalized:
            case_no = params[0]
            self.current = [{"restarted": 1}] if case_no == "CASE-RESTART" else []
            return
        if "FROM case_staff_assignments csa" in normalized and "LEFT JOIN staff" in normalized:
            case_no = params[0]
            self.current = list(self.connection.completed_assignments.get(case_no, ()))
            return
        if "FROM orders WHERE case_no IN" in normalized:
            self.current = list(self.connection.order_snapshot)
            return
        if "FROM case_staff_assignments WHERE case_no IN" in normalized:
            self.current = list(self.connection.assignment_snapshot)
            return
        if "FROM staff_schedule ss JOIN case_staff_assignments" in normalized:
            self.current = list(self.connection.schedule_snapshot)
            return
        raise AssertionError(f"unexpected read query: {normalized}")

    def fetchone(self):
        return self.current[0] if self.current else None

    def fetchall(self):
        return list(self.current)


class _Connection:
    def __init__(self):
        self.executed = []
        self.order_snapshot = [
            {"case_no": "CASE-OK", "status": "歷史訂單", "actual_start_date": date(2025, 10, 7), "actual_end_date": date(2025, 11, 17)},
            {"case_no": "CASE-RESTART", "status": "洽談中", "actual_start_date": None, "actual_end_date": None},
        ]
        self.assignment_snapshot = [
            {"id": 41, "case_no": "CASE-OK", "staff_id": 7, "status": "completed", "assigned_start_date": date(2025, 10, 7), "assigned_end_date": date(2025, 11, 17)},
            {"id": 42, "case_no": "CASE-RESTART", "staff_id": 8, "status": "completed", "assigned_start_date": date(2025, 9, 1), "assigned_end_date": date(2025, 9, 30)},
        ]
        self.schedule_snapshot = []
        self.completed_assignments = {
            "CASE-OK": (
                {
                    "assignment_id": 41,
                    "case_no": "CASE-OK",
                    "staff_id": 7,
                    "status": "completed",
                    "assigned_start_date": date(2025, 10, 7),
                    "assigned_end_date": date(2025, 11, 17),
                    "staff_exists": 7,
                    "staff_name": "黃欣",
                },
            ),
            "CASE-RESTART": (
                {
                    "assignment_id": 42,
                    "case_no": "CASE-RESTART",
                    "staff_id": 8,
                    "status": "completed",
                    "assigned_start_date": date(2025, 9, 1),
                    "assigned_end_date": date(2025, 9, 30),
                    "staff_exists": 8,
                    "staff_name": "舊月嫂",
                },
            ),
        }

    def cursor(self):
        return _Cursor(self)


def _write_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "歷史訂單"
    sheet.append(["client_name", "case_no", "start_date", "end_date", "status", "staff_name"])
    sheet.append(["可顯示客戶", "CASE-OK", "2025-10-07", "2025-11-17", 1, "黃欣"])
    sheet.append(["缺人客戶", "CASE-NO-STAFF", "2025-10-07", "2025-11-17", 1, None])
    sheet.append(["缺日期客戶", "CASE-BAD-DATE", "bad-date", "2025-11-17", 1, "黃欣"])
    sheet.append(["缺指派客戶", "CASE-NO-ASSIGNMENT", "2025-10-07", "2025-11-17", 1, "黃欣"])
    sheet.append(["未服務客戶", "CASE-DISCUSSION", None, None, 2, "黃欣"])
    sheet.append(["已重啟客戶", "CASE-RESTART", "2025-09-01", "2025-09-30", 1, "舊月嫂"])
    workbook.save(path)


def test_health_check_replays_five_categories_and_proves_zero_writes(tmp_path):
    workbook_path = tmp_path / "historical_orders.xlsx"
    _write_workbook(workbook_path)
    connection = _Connection()
    monthly_calls = []

    def monthly_reader(staff_id, year, month):
        monthly_calls.append((staff_id, year, month))
        return {
            "staff_id": staff_id,
            "year": year,
            "month": month,
            "days": [
                {
                    "work_date": "2025-10-07",
                    "status": "historical_assignment",
                    "assignment_id": 41,
                    "case_no": "CASE-OK",
                }
            ],
            "schedule_map": {},
        }

    first = run_historical_calendar_health_check(
        str(workbook_path),
        connection=connection,
        monthly_reader=monthly_reader,
    )
    second = run_historical_calendar_health_check(
        str(workbook_path),
        connection=connection,
        monthly_reader=monthly_reader,
    )

    assert first["category_counts"] == {
        "可顯示": 1,
        "缺服務人員": 1,
        "缺有效日期": 1,
        "缺已完成指派": 1,
        "不應顯示": 2,
    }
    categories = {item["case_no"]: item for item in first["rows"]}
    assert categories["CASE-OK"]["category"] == "可顯示"
    assert categories["CASE-NO-STAFF"]["category"] == "缺服務人員"
    assert categories["CASE-BAD-DATE"]["category"] == "缺有效日期"
    assert categories["CASE-NO-ASSIGNMENT"]["category"] == "缺已完成指派"
    assert categories["CASE-NO-ASSIGNMENT"]["source_staff"] == ["黃欣"]
    assert categories["CASE-DISCUSSION"]["category"] == "不應顯示"
    assert categories["CASE-RESTART"] == {
        "source_row": 7,
        "case_no": "CASE-RESTART",
        "client_name": "已重啟客戶",
        "source_status": "deposit_paid",
        "category": "不應顯示",
        "reason": "precision_restart_suppresses_historical_assignment",
    }
    assert first["root_facts_unchanged"] is True
    assert first["root_fact_digest"] == second["root_fact_digest"]
    assert first["rows"] == second["rows"]
    assert monthly_calls == [(7, 2025, 10), (7, 2025, 10)]
    assert all(sql.upper().startswith("SELECT ") for sql, _params in connection.executed)
