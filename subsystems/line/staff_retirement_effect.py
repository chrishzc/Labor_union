"""Adapt committed Staff retirement transitions to LINE staff-role revocation."""

from __future__ import annotations

from domains.staff.retirement import StaffLifecycleTransition
from subsystems.line.identity_management_application import (
    request_staff_retirement_revocation,
)


class LineStaffRetirementEffect:
    def on_transition(self, unit_of_work, request, preview, receipt) -> None:
        if request.transition is not StaffLifecycleTransition.RETIRE:
            return
        request_staff_retirement_revocation(
            unit_of_work,
            staff_id=receipt.staff_id,
            lifecycle_version=receipt.version,
            correlation_id=request.correlation_id,
        )


__all__ = ["LineStaffRetirementEffect"]
