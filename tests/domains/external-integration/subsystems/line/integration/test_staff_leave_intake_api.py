"""File: test_staff_leave_intake_api.py
Description: 驗證月嫂請假 LIFF 的 Preview、Apply 與 staff-scoped readback 契約。
"""

from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace

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
from shared_kernel.fingerprints import fingerprint_payload
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



@pytest.mark.parametrize(
    ("staff_id", "line_user", "accepted", "expected"),
    [
        (7, "U-original", False, "draft_saved"),
        (7, "U-original", True, "group_received"),
        (8, "U-original", True, "not_received"),
        (7, "U-foreign", True, "not_received"),
    ],
)
def test_postponement_receipt_uses_original_actor_and_group_event(monkeypatch, staff_id, line_user, accepted, expected):
    case_no = "SYNTHETIC"
    key = "91af7142-1111-4111-8111-fa1c00b1f00d"
    unit = SimpleNamespace(_connection=object())
    calls = []
    draft = {
        "staff_id": 7,
        "assignment_id": 10,
        "line_actor_fingerprint": fingerprint_payload({"line_user_id": "U-original"}).value,
        "group_binding_version": 3,
    }

    def load(unit_of_work, family, case, proposal_ref):
        assert unit_of_work is unit
        assert family == staff_leave_intake.POSTPONEMENT_DRAFT_FAMILY
        assert case == case_no
        assert proposal_ref == staff_leave_intake.postponement_proposal_ref(case_no, key)
        return draft

    def require_assignment(_, case, staff, assignment, changes):
        assert (case, staff, assignment, changes) == (case_no, 7, 10, ())
        calls.append("assignment")

    def observed_group(unit_of_work, case, proposal_ref):
        assert unit_of_work is unit
        assert case == case_no
        assert proposal_ref == staff_leave_intake.postponement_proposal_ref(case_no, key)
        calls.append("group")
        return accepted

    monkeypatch.setattr(staff_leave_intake, "_verified_staff_context", lambda _: (LineUserId(line_user), {"staff_id": staff_id}))
    monkeypatch.setattr(staff_leave_intake, "open_line_unit_of_work", lambda: nullcontext(unit))
    monkeypatch.setattr(staff_leave_intake, "load_group_helper_proposal", load)
    monkeypatch.setattr(staff_leave_intake, "build_service_start_application", lambda _: object())
    monkeypatch.setattr(staff_leave_intake, "postponement_group_binding", lambda *_: SimpleNamespace(version=SimpleNamespace(value=3)))
    monkeypatch.setattr(staff_leave_intake, "require_postponement_assignment", require_assignment)
    monkeypatch.setattr(staff_leave_intake, "postponement_group_received", observed_group)

    result = staff_leave_intake.leave_defer_status(staff_leave_intake.StaffLeaveDeferStatusRequest(
        case_no=case_no, assignment_id=10, idempotency_key=key,
    )).data

    if expected == "not_received":
        assert result == {"status": "not_received"}
        assert calls == []
    else:
        assert result == {"status": expected, "case_no": case_no, "assignment_id": 10, "idempotency_key": key}
        assert calls == ["assignment", "group"]
