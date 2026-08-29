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


def test_preview_returns_business_fields_and_opaque_transport_fingerprint(monkeypatch):
    monkeypatch.setattr(
        staff_leave_intake,
        "_verified_staff_context",
        lambda _: (LineUserId("U-private"), STAFF),
    )

    result = staff_leave_intake.preview_staff_leave_request(
        StaffLeaveRequestCreate(
            leave_start_date=date(2026, 8, 20),
            leave_end_date=date(2026, 8, 21),
            leave_reason="返鄉",
        )
    )

    assert result.data["staff_name"] == "測試月嫂"
    assert result.data["can_apply"] is True
    assert len(result.data["preview_fingerprint"]) == 64
    assert "line_user_id" not in result.data


def test_apply_rejects_changed_intent_against_preview(monkeypatch):
    class FakeApplication:
        def apply(self, _command, _fingerprint):
            raise StaffLeaveIntakeWorkflowError("leave_request_preview_stale")

    monkeypatch.setattr(
        staff_leave_intake,
        "_verified_staff_context",
        lambda _: (LineUserId("U-private"), STAFF),
    )

    body = StaffLeaveRequestApply(
        leave_start_date=date(2026, 8, 20),
        leave_end_date=date(2026, 8, 21),
        leave_reason="返鄉",
        preview_fingerprint="a" * 64,
    )
    with pytest.raises(HTTPException) as captured:
        staff_leave_intake.apply_staff_leave_request(body, "leave-1", FakeApplication())

    assert captured.value.status_code == 409
    assert captured.value.detail == {"code": "leave_request_preview_stale"}


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
