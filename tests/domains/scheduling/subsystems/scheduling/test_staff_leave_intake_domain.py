"""File: test_staff_leave_intake_domain.py
Description: 驗證 LINE 請假待辦不冒充正式排班的狀態規則。"""

from datetime import date

import pytest

from domains.scheduling.staff_leave_intake import (
    StaffLeaveRequestDomainError,
    StaffLeaveRequestIntent,
    StaffLeaveRequestIssue,
    StaffLeaveRequestStatus,
    transition_request,
)


def test_staff_can_cancel_only_while_request_is_pending():
    assert transition_request(
        StaffLeaveRequestStatus.PENDING,
        action="cancel",
        actor_is_staff=True,
        reason="行程變更",
    ) is StaffLeaveRequestStatus.CANCELLED
    with pytest.raises(StaffLeaveRequestDomainError) as error:
        transition_request(
            StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING,
            action="cancel",
            actor_is_staff=True,
            reason="太晚了",
        )
    assert error.value.issue is StaffLeaveRequestIssue.INVALID_TRANSITION


def test_only_accepted_request_can_be_resolved_after_canonical_apply():
    assert transition_request(
        StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING,
        action="resolve",
        actor_is_staff=False,
    ) is StaffLeaveRequestStatus.RESOLVED
    with pytest.raises(StaffLeaveRequestDomainError):
        transition_request(StaffLeaveRequestStatus.PENDING, action="resolve", actor_is_staff=False)


def test_invalid_date_range_is_rejected_before_any_persistence():
    with pytest.raises(StaffLeaveRequestDomainError) as error:
        StaffLeaveRequestIntent(date(2026, 8, 16), date(2026, 8, 15))
    assert error.value.issue is StaffLeaveRequestIssue.INVALID_DATE_RANGE
