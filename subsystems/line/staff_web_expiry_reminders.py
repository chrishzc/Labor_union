from datetime import datetime

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from domains.staff.retirement import StaffLifecycleState
from shared_kernel.clock import TAIPEI_TIME_ZONE
from shared_kernel.identities import CorrelationId, IdempotencyKey, IdempotencyReceipt
from subsystems.line.message_copy import configured_text, copy_template_id


SOURCE = "staff_web_expiry_reminder"
COPY_KEY = "staff-web-expiry-reminder"
DEFAULT_COPY = "您的個人網頁項目「{item_name}」將於 {expiry_date} 到期。請從 LINE「我的資料」提交新的照片與到期日。"


class StaffWebExpiryReminderWorker:
    run_before_delivery = True

    def __init__(self, unit_of_work_factory, now):
        self._unit = unit_of_work_factory
        self._now = now

    def run_once(self) -> int:
        today = self._now().astimezone(TAIPEI_TIME_ZONE).date()
        count, after, limit = 0, 0, 100
        while True:
            with self._unit() as unit:
                candidates = unit.staff_web_profiles.reminder_candidates(today, after, limit)
            for row in candidates:
                count += self._queue(row.staff_id, row.entry_id)
            if len(candidates) < limit:
                return count
            after = candidates[-1].entry_id

    def _queue(self, staff_id: int, entry_id: int) -> int:
        now = self._now()
        with self._unit() as unit:
            binding = _active_binding(unit, staff_id, lock_staff=True)
            if binding is None:
                return 0
            photo = unit.staff_web_profiles.entry(staff_id, entry_id, lock=True)
            if not _due(photo, now):
                return 0
            key = IdempotencyKey(f"staff-web-expiry:{entry_id}:{photo.version}")
            if unit.receipts.get(key, for_update=True) is not None or unit.delivery_tasks.exists_for_key(key):
                return 0
            fields = {"item_name": photo.item.name, "expiry_date": photo.expiry_date.isoformat()}
            text = configured_text(unit, copy_template_id(COPY_KEY), DEFAULT_COPY.format(**fields), fields)
            request = LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, binding.line_user_id),
                LineMessageKind.TEXT, canonical_line_payload_json({"type": "text", "text": text}),
                now, key, CorrelationId(key.value), SOURCE,
                f"{staff_id}:{entry_id}:{photo.version}:{binding.version.value}",
            )
            task = unit.delivery_tasks.enqueue(request)
            unit.receipts.append(IdempotencyReceipt(key, request.fingerprint, f"line-delivery:{task.task_id.value}"))
            unit.commit()
            return 1


def staff_web_expiry_delivery_is_current(unit, task, now: datetime) -> bool:
    request = task.request
    if request.source_aggregate_type != SOURCE:
        return True
    try:
        staff_id, entry_id, version, binding_version = map(int, request.source_aggregate_identity.split(":"))
    except ValueError:
        return False
    photo = unit.staff_web_profiles.entry(staff_id, entry_id)
    if not _due(photo, now) or photo.version != version:
        return False
    binding = _active_binding(unit, staff_id, lock_staff=False)
    return (
        binding is not None and binding.version.value == binding_version
        and request.recipient.recipient_type is LineRecipientType.USER
        and binding.line_user_id == request.recipient.identity
    )


def _due(photo, now: datetime) -> bool:
    return photo is not None and photo.item.reminder_due(
        photo.expiry_date, now.astimezone(TAIPEI_TIME_ZONE).date(),
    )


def _active_binding(unit, staff_id: int, *, lock_staff: bool):
    try:
        lifecycle = unit.staff_lifecycle.load(staff_id, lock=lock_staff)
    except ValueError:
        return None
    if lifecycle.state is not StaffLifecycleState.ACTIVE:
        return None
    binding = unit.identities.get_by_subject(LineBindingSubjectType.STAFF, str(staff_id))
    return binding if binding and binding.status is LineIdentityBindingStatus.BOUND else None
