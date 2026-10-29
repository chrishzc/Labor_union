"""Union-only log reminder actions; queries never enqueue or call LINE."""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Protocol

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineGroupId
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
from subsystems.scheduling.service_day_log_workflow import ServiceDayLogGap

SOURCE_TYPE = "manual_service_day_log_reminder"
PREFIX = "service-day-log-reminder:"


def reminder_text(staff_name: str) -> str:
    return f"請 {staff_name} 補上尚未填寫的服務日誌，謝謝。"


@dataclass(frozen=True, slots=True)
class ServiceDayLogReminder:
    gap: ServiceDayLogGap
    group_label: str
    can_send: bool
    message: str | None = None


@dataclass(frozen=True, slots=True)
class SendServiceDayLogReminder:
    case_no: str
    staff_id: int
    missing_from: date
    missing_through: date
    idempotency_key: str

    def __post_init__(self):
        if self.missing_through < self.missing_from:
            raise ValueError("service_day_log_reminder_date_invalid")

    @property
    def correlation(self):
        return CorrelationId(f"{PREFIX}{self.staff_id}:{self.missing_from.isoformat()}:{self.missing_through.isoformat()}")


class ServiceDayLogReminderPort(Protocol):
    def list(self, now: datetime, page: int, page_size: int): ...
    def recipient(self, command: SendServiceDayLogReminder, now: datetime): ...
    def enqueue(self, request: LineDeliveryRequest): ...
    def replay(self, command: SendServiceDayLogReminder): ...
    def delivery_is_current(self, task: object, now: datetime) -> bool: ...


class ServiceDayLogReminderApplication:
    def __init__(self, repository: ServiceDayLogReminderPort, unit_of_work_factory, now, copy_reader: Callable[[str], str] | None = None):
        self.repository = repository
        self._unit = unit_of_work_factory
        self._now = now
        self._copy_reader = copy_reader or reminder_text

    def list(self, page=1, page_size=25):
        return self.repository.list(self._now(), page, page_size)

    def send(self, command: SendServiceDayLogReminder):
        with self._unit() as unit:
            replay = self.repository.replay(command)
            if replay is not None:
                unit.commit()
                return replay
            recipient = self.repository.recipient(command, self._now())
            if recipient is None:
                raise ValueError("service_day_log_reminder_no_longer_applicable")
            group_id, staff_name, group_version = recipient
            result = self.repository.enqueue(LineDeliveryRequest(
                LineRecipient(LineRecipientType.GROUP, LineGroupId(group_id)), LineMessageKind.TEXT,
                canonical_line_payload_json({"type": "text", "text": self._copy_reader(staff_name)}),
                self._now(), IdempotencyKey(f"service-day-log-manual:{command.idempotency_key}"),
                CorrelationId(command.correlation.value + f":{group_version}"), SOURCE_TYPE, command.case_no))
            unit.commit()
            return result


def service_day_log_reminder_delivery_is_current(unit, task, now):
    request = task.request
    # Retired automatic private reminders must never cross the provider boundary.
    automatic = request.correlation_id.value.startswith("line-notification:scheduling-service-day-checkpoint-outbox:")
    if not automatic and request.source_aggregate_type != SOURCE_TYPE:
        return True
    repository = getattr(unit, "service_day_log_reminders", None)
    if not automatic and repository is not None and repository.delivery_is_current(task, now):
        return True
    unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(
        task.task_id, ActorContext("line-service-day-log-reminder"),
        IdempotencyKey(f"service-day-log-reminder-stale:{task.task_id.value}"), request.correlation_id))
    unit.commit()
    return False
