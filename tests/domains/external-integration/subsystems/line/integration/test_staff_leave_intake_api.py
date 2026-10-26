"""File: test_staff_leave_intake_api.py
Description: 驗證月嫂請假 LIFF 的 Preview、Apply 與 staff-scoped readback 契約。
"""

from datetime import date

import pytest
from fastapi import HTTPException

from api.routes import staff_leave_intake
from api.schemas.line_staff_self_service import (
    StaffLeaveRequestApply,
    StaffLeaveRequestCreate,
    StaffLiffRequest,
)
from domains.line.identities import LineUserId
from domains.scheduling.staff_leave_intake import StaffLeaveRequestStatus
from subsystems.scheduling.staff_leave_intake_workflow import (
    StaffLeaveIntakeWorkflowError,
    StaffLeaveRequestSnapshot,
)


STAFF = {"staff_id": 7, "staff_name": "測試月嫂"}


class FakeConnection:
    def close(self):
        pass


def _snapshot() -> StaffLeaveRequestSnapshot:
    return StaffLeaveRequestSnapshot(
        31,
        7,
        "U-private",
        StaffLeaveRequestStatus.PENDING,
        1,
        "a" * 64,
        date(2026, 8, 20),
        date(2026, 8, 21),
        "返鄉",
    )


def test_old_preview_requires_reopening_current_leave_result_entry(monkeypatch):
    monkeypatch.setattr(staff_leave_intake,'_verified_staff_context',lambda _:(LineUserId('U-private'),STAFF))
    body=StaffLeaveRequestApply(leave_start_date=date(2027,1,5),leave_end_date=date(2027,1,6),leave_reason='',preview_fingerprint='a'*64)
    with pytest.raises(HTTPException) as error:
        staff_leave_intake.preview_staff_leave_request(body)
    assert error.value.status_code==410
    assert error.value.detail["code"]=="leave_intake_replaced"


def test_old_apply_cannot_create_pending_requests(monkeypatch):
    monkeypatch.setattr(staff_leave_intake,'_verified_staff_context',lambda _:(LineUserId('U-private'),STAFF))
    body=StaffLeaveRequestApply(leave_start_date=date(2027,1,5),leave_end_date=date(2027,1,6),leave_reason='',preview_fingerprint='a'*64)
    with pytest.raises(HTTPException) as error:
        staff_leave_intake.apply_staff_leave_request(body,"same-key",object())
    assert error.value.status_code==410
    assert error.value.detail["code"]=="leave_intake_replaced"


def test_readback_is_scoped_to_verified_staff_and_redacts_line_identity(monkeypatch):
    class FakeRepository:
        def __init__(self, _connection):
            pass

        def load_for_staff(self, request_id, staff_id):
            assert request_id == 31
            assert staff_id == 7
            return _snapshot()

    monkeypatch.setattr(
        staff_leave_intake,
        "_verified_staff_context",
        lambda _: (LineUserId("U-private"), STAFF),
    )
    monkeypatch.setattr(staff_leave_intake, "get_connection", lambda: FakeConnection())
    monkeypatch.setattr(staff_leave_intake, "MySqlStaffLeaveIntakeRepository", FakeRepository)

    result = staff_leave_intake.query_staff_leave_request(31, StaffLiffRequest())

    assert result.data["request_id"] == 31
    assert result.data["status"] == "pending"
    assert result.data["leave_reason"] == "返鄉"
    assert "line_user_id" not in result.data
    assert "request_fingerprint" not in result.data
