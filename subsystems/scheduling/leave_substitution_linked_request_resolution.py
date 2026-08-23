"""
File: leave_substitution_linked_request_resolution.py
Description: 在請假代班outer UoW內鎖定、結案Staff leave request並建立durable LINE intent。
"""

from __future__ import annotations

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineUserId
from domains.scheduling.staff_leave_intake import StaffLeaveRequestStatus
from shared_kernel.clock import BusinessClock
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.scheduling.leave_substitution_workflow import (
    LinkedLeaveRequestIntent,
    LinkedLeaveRequestResolutionError,
    LinkedLeaveRequestResult,
)
from subsystems.scheduling.staff_leave_intake_workflow import (
    ResolveStaffLeaveRequest,
    StaffLeaveIntakeWorkflow,
    StaffLeaveIntakeWorkflowError,
)


class LeaveSubstitutionLinkedRequestResolution:
    def __init__(self, repository, line_delivery_repository, clock: BusinessClock) -> None:
        self._repository = repository
        self._workflow = StaffLeaveIntakeWorkflow(repository)
        self._line_delivery_repository = line_delivery_repository
        self._clock = clock

    def preview(
        self,
        intent: LinkedLeaveRequestIntent | None,
    ) -> LinkedLeaveRequestResult | None:
        if intent is None:
            return None
        snapshot = self._repository.load(intent.request_id)
        return self._validated_snapshot(intent, snapshot)

    def lock_for_apply(
        self,
        intent: LinkedLeaveRequestIntent | None,
    ) -> LinkedLeaveRequestResult | None:
        if intent is None:
            return None
        snapshot = self._repository.load_for_update(intent.request_id)
        return self._validated_snapshot(intent, snapshot)

    def resolve_and_enqueue(
        self,
        locked: LinkedLeaveRequestResult | None,
        *,
        receipt_key: str,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> LinkedLeaveRequestResult | None:
        if locked is None:
            return None
        resolution_key = _resolution_key(
            idempotency_key,
            locked.request_id,
            receipt_key,
        )
        try:
            resolved = self._workflow.resolve(
                ResolveStaffLeaveRequest(
                    locked.request_id,
                    locked.expected_version,
                    receipt_key,
                    resolution_key,
                )
            )
            self._line_delivery_repository.enqueue(
                _completion_notification(
                    resolved,
                    correlation_id,
                    resolution_key,
                    self._clock,
                )
            )
        except StaffLeaveIntakeWorkflowError as error:
            raise LinkedLeaveRequestResolutionError(str(error)) from error
        except ValueError as error:
            raise LinkedLeaveRequestResolutionError(str(error)) from error
        return LinkedLeaveRequestResult(
            resolved.request_id,
            locked.expected_version,
            resolved.version,
            resolved.status.value,
            receipt_key,
            "enqueued",
            resolved.staff_id,
        )

    @staticmethod
    def _validated_snapshot(intent, snapshot):
        if snapshot is None:
            raise LinkedLeaveRequestResolutionError("leave_request_not_found")
        if snapshot.version != intent.expected_version:
            raise LinkedLeaveRequestResolutionError("leave_request_stale")
        if snapshot.status is not StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING:
            raise LinkedLeaveRequestResolutionError("leave_request_not_resolvable")
        return LinkedLeaveRequestResult(
            snapshot.request_id,
            intent.expected_version,
            None,
            snapshot.status.value,
            None,
            "not_requested",
            snapshot.staff_id,
        )


def _resolution_key(
    key: IdempotencyKey,
    request_id: int,
    receipt_key: str,
) -> str:
    return "staff-leave-resolve:" + fingerprint_payload(
        {
            "apply_key": key.value,
            "request_id": request_id,
            "receipt_key": receipt_key,
        }
    ).value


def _completion_notification(snapshot, correlation_id, resolution_key, clock):
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId(snapshot.line_user_id)),
        LineMessageKind.TEXT,
        canonical_line_payload_json(
            {"type": "text", "text": "您的請假申請已完成正式排班處理。"}
        ),
        clock.now(),
        IdempotencyKey(
            "staff-leave-notify:"
            + fingerprint_payload({"resolution_key": resolution_key}).value
        ),
        correlation_id,
        "scheduling_staff_leave_request",
        str(snapshot.request_id),
    )
