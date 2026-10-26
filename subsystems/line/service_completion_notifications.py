"""One case-group survey invitation from a committed normal service completion."""

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol

from domains.line.canonical_payload import canonical_line_payload_json
from subsystems.line.notification_policy import NotificationSourceEvent

EVENT_CODE = 'order.service_completed'
SOURCE_TYPE = 'order_service_completion'


@dataclass(frozen=True, slots=True)
class ServiceCompletionNotification:
    case_no: str
    completion_identity: str
    lifecycle_event_id: int
    order_version: int
    group_id: str | None
    group_version: int

    def facts(self):
        return asdict(self)

    def event(self, now: datetime) -> NotificationSourceEvent:
        facts = self.facts()
        identity = sha256(canonical_line_payload_json(facts).encode('utf-8')).hexdigest()
        return NotificationSourceEvent('service-completed:'+identity, EVENT_CODE, False, facts,
            source_domain='orders', source_aggregate_type=SOURCE_TYPE,
            source_aggregate_identity=self.case_no, source_version=self.order_version, occurred_at=now)


class ServiceCompletionNotificationPort(Protocol):
    def delivery_is_current(self, task: object) -> bool: ...


def service_completion_delivery_is_current(unit, task):
    if task.request.source_aggregate_type != SOURCE_TYPE:
        return True
    if unit.service_completion_notifications.delivery_is_current(task):
        return True
    from shared_kernel.identities import ActorContext, IdempotencyKey
    from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
    unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,
        ActorContext('line-service-completion'), IdempotencyKey(f'completion-stale:{task.task_id.value}'),
        task.request.correlation_id))
    unit.commit()
    return False
