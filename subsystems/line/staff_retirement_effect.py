"""Adapt committed Staff retirement transitions to LINE staff-role revocation."""

from __future__ import annotations

from domains.staff.retirement import StaffLifecycleTransition
from subsystems.line.identity_management_application import (
    request_staff_retirement_revocation,
)
from subsystems.line.notification_policy import NotificationSourceEvent


class LineStaffRetirementEffect:
    def on_transition(self, unit_of_work, request, preview, receipt) -> None:
        if request.transition is not StaffLifecycleTransition.RETIRE:
            return
        revocation = request_staff_retirement_revocation(
            unit_of_work,
            staff_id=receipt.staff_id,
            lifecycle_version=receipt.version,
            correlation_id=request.correlation_id,
        )
        if revocation is None:
            return
        unit_of_work.notification_rules.register_and_project(
            NotificationSourceEvent(
                identity=f"staff-retirement:{receipt.staff_id}:{receipt.version}",
                event_code="staff.retirement.committed",
                historical_silent=False,
                facts={
                    "staff_id": receipt.staff_id,
                    "resulting_state": receipt.state.value,
                    "line_user_id": revocation.line_user_id.value,
                    "recipient_projection": {
                        "selector": "staff.binding_owner",
                        "type": "user",
                        "identity": revocation.line_user_id.value,
                    },
                },
                source_domain="staff",
                source_aggregate_type="staff_lifecycle",
                source_aggregate_identity=str(receipt.staff_id),
                source_version=receipt.version,
                occurred_at=request.effective_at,
            )
        )


__all__ = ["LineStaffRetirementEffect"]
