"""Shared dismissal of a current recommendation signing reminder."""

from hashlib import sha256
from types import TracebackType
from typing import Callable, Protocol

from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, IdempotencyKey, IdempotencyReceipt
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.ports import LineAuditIntent, LineAuditPort, LineIdempotencyReceiptPort

SIGNING_REMINDER = "notification_signing_reminder"
SIGNING_REMINDER_DISMISSED = "notification_signing_reminder_dismissed"


class SigningReminderConflict(RuntimeError):
    pass


class SigningReminderSource(Protocol):
    def lock_recommendation_plan(self, plan_id: int) -> None: ...
    def current_signing_reminder(self, plan_id: int, occurrence: str) -> bool: ...


class SigningReminderUnitOfWork(Protocol):
    def __enter__(self) -> object: ...

    def __exit__(self, exception_type: type[BaseException] | None, exception: BaseException | None,
                 traceback: TracebackType | None) -> bool: ...

    @property
    def matching_notifications(self) -> SigningReminderSource: ...

    @property
    def receipts(self) -> LineIdempotencyReceiptPort: ...

    @property
    def audit(self) -> LineAuditPort: ...

    def commit(self) -> None: ...


def dismiss_signing_reminder(
    uow_factory: Callable[[], SigningReminderUnitOfWork],
    plan_id: int,
    occurrence: str,
    request_key: IdempotencyKey,
    actor: ActorContext,
) -> bool:
    require_line_capability(actor, LineCapability.MATCHING_READ)
    require_line_capability(actor, LineCapability.MATCHING_OVERRIDE)
    target = f"recommendation:{plan_id}:awaiting_signing:{occurrence}"
    reason = "使用者移除提醒"
    snapshot = {"actor_id": actor.actor_id, "reminder": target, "reason": reason}
    fingerprint = fingerprint_payload(snapshot)
    request_hash = sha256(f"{actor.actor_id}:{request_key.value}".encode()).hexdigest()
    request_receipt = IdempotencyReceipt(IdempotencyKey(f"notification-signing-request:{request_hash}"), fingerprint, target)
    unit = uow_factory()
    with unit:
        unit.matching_notifications.lock_recommendation_plan(plan_id)
        previous = unit.receipts.get(request_receipt.key)
        if previous is not None:
            if previous != request_receipt:
                raise SigningReminderConflict("notification_reminder_idempotency_conflict")
            return True
        if not unit.matching_notifications.current_signing_reminder(plan_id, occurrence):
            raise SigningReminderConflict("notification_reminder_changed")
        try:
            unit.receipts.append(request_receipt, result_snapshot=snapshot)
        except RuntimeError as error:
            if str(error) != "line_idempotency_receipt_conflict":
                raise
            raise SigningReminderConflict("notification_reminder_idempotency_conflict") from error
        unit.audit.append(LineAuditIntent(SIGNING_REMINDER_DISMISSED, actor.actor_id, SIGNING_REMINDER, occurrence))
        unit.commit()
        return False
