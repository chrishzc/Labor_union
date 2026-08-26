"""File: test_service_day_log_repository.py
Description: 驗證寶寶日誌 repository 的鎖定與 terminal replay owner 邊界。"""

from datetime import date

import pytest

from domains.scheduling.service_day_log import ServiceDayLogIntent
from infrastructure.mysql.service_day_log_repository import MySqlServiceDayLogRepository
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.scheduling.service_day_log_workflow import ApplyServiceDayLog


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class FakeConnection:
    def __init__(self, rows):
        self.cursor_value = FakeCursor(rows)

    def cursor(self):
        return self.cursor_value


def _command(line_user_id="U-caregiver"):
    return ApplyServiceDayLog(9, line_user_id, 12, ServiceDayLogIntent(date(2026, 8, 16), "寶寶正常", ()), "log-key", PreviewFingerprint("a" * 64))


def _row(**overrides):
    return {"id": 1, "case_no": "CASE-1", "assignment_id": 12, "staff_id": 9, "staff_line_user_id": "U-caregiver", "service_date": date(2026, 8, 16), "baby_log_text": "寶寶正常", "requires_cooking": 0, "content_fingerprint": "a" * 64, **overrides}


def test_assignment_preview_query_does_not_lock_but_apply_does() -> None:
    connection = FakeConnection([{"case_no": "CASE-1", "requires_cooking": 0}, {"case_no": "CASE-1", "requires_cooking": 0}])
    repository = MySqlServiceDayLogRepository(connection)

    repository.load_assignment(9, 12, date(2026, 8, 16), for_update=False)
    repository.load_assignment(9, 12, date(2026, 8, 16), for_update=True)

    assert "FOR UPDATE" not in connection.cursor_value.executed[0][0]
    assert connection.cursor_value.executed[1][0].endswith("FOR UPDATE")


def test_terminal_replay_requires_exact_staff_owner_and_fingerprint() -> None:
    repository = MySqlServiceDayLogRepository(FakeConnection([_row()]))

    result = repository.load_replay(_command())

    assert result is not None and result.outcome == "existing"
    with pytest.raises(ValueError, match="service_day_log_idempotency_conflict"):
        MySqlServiceDayLogRepository(FakeConnection([_row()])).load_replay(_command("U-other"))
