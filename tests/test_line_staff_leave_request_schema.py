"""File: test_line_staff_leave_request_schema.py
Description: 驗證月嫂 LIFF 請假 payload 不可夾帶代班主檔資訊。"""

import pytest
from pydantic import ValidationError

from api.schemas.line_staff_self_service import StaffLeaveRequestCancel, StaffLeaveRequestCreate
from api.routes.leave_substitution import LeaveSubstitutionApplyBody


def test_leave_request_rejects_substitute_identity_fields():
    with pytest.raises(ValidationError):
        StaffLeaveRequestCreate.model_validate(
            {
                "leave_start_date": "2026-08-20",
                "leave_end_date": "2026-08-20",
                "substitute_name": "不可信候選人",
            }
        )


def test_leave_request_accepts_dates_and_optional_reason_only():
    payload = StaffLeaveRequestCreate.model_validate(
        {"leave_start_date": "2026-08-20", "leave_end_date": "2026-08-21", "leave_reason": "家務"}
    )
    assert payload.leave_reason == "家務"


def test_canonical_apply_requires_request_version_when_linking_leave_request():
    body = LeaveSubstitutionApplyBody.model_validate({
        "original_assignment_id": 1,
        "items": [],
        "expected_order_version": 1,
        "expected_scheduling_version": 1,
        "expected_client_finance_version": 1,
        "expected_payroll_version": 1,
        "preview_fingerprint": "0" * 64,
        "reason": "正式處理",
        "leave_request_id": 7,
    })
    assert body.leave_request_id == 7
    assert body.expected_leave_request_version is None


def test_leave_request_cancel_requires_reason_and_expected_version():
    with pytest.raises(ValidationError):
        StaffLeaveRequestCancel.model_validate({"expected_version": 1, "reason": ""})
