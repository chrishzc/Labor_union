"""Second-payment group notifications, backed by current Finance facts only."""
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from typing import Protocol

from domains.line.canonical_payload import canonical_line_payload_json
from subsystems.line.notification_policy import NotificationSourceEvent

REMINDER = 'client_second_payment_reminder'
SETTLED = 'client_second_payment_settled'
DUE_EVENT = 'client.second_payment_due'
SETTLED_EVENT = 'client.second_payment_settled'


@dataclass(frozen=True, slots=True)
class SecondPaymentNotification:
    case_no: str
    obligation_identity: str
    account_version: int
    obligation_event_id: int
    due_date: date
    required_amount: int
    remaining_amount: int
    group_id: str | None
    settled: bool = False
    settlement_identity: str | None = None
    settled_amount: int = 0
    group_version: int = 0

    def facts(self):
        return {'case_no': self.case_no, 'obligation_identity': self.obligation_identity,
                'account_version': self.account_version, 'obligation_event_id': self.obligation_event_id,
                'second_payment_due_date': self.due_date.isoformat(), 'required_amount_ntd': self.required_amount,
                'remaining_amount_ntd': self.remaining_amount, 'group_id': self.group_id,
                'group_version': self.group_version,
                'settled': self.settled,
                'settlement_identity': self.settlement_identity, 'settled_amount_ntd': self.settled_amount}

    def event(self, now: datetime) -> NotificationSourceEvent:
        paid = self.settlement_identity is not None
        if self.required_amount <= 0 or (self.settled_amount if paid else self.remaining_amount) <= 0:
            raise ValueError('second_payment_not_required_or_already_settled')
        facts = self.facts()
        token = sha256(canonical_line_payload_json(facts).encode('utf-8')).hexdigest()
        facts['second_payment_amount'] = f'{self.settled_amount if paid else self.remaining_amount:,}'
        return NotificationSourceEvent(
            identity=('second-payment-settled:' if paid else 'second-payment-due:') + token,
            event_code=SETTLED_EVENT if paid else DUE_EVENT, historical_silent=False,
            facts=facts, source_domain='client_finance', source_aggregate_type=SETTLED if paid else REMINDER,
            source_aggregate_identity=self.case_no, source_version=self.account_version, occurred_at=now,
        )


class SecondPaymentNotificationPort(Protocol):
    def delivery_is_current(self, task: object, now: datetime) -> bool: ...


def second_payment_delivery_is_current(unit, task, now):
    from shared_kernel.identities import ActorContext, IdempotencyKey
    from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand

    request = task.request
    retired = request.correlation_id.value.startswith('line-notification:order-second-payment-reminder:')
    retired = retired or request.source_aggregate_type in (REMINDER, SETTLED)
    if not retired and request.source_aggregate_type not in (REMINDER, SETTLED):
        return True
    if not retired and unit.second_payment_notifications.delivery_is_current(task, now):
        return True
    unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id, ActorContext('line-second-payment-worker'),
        IdempotencyKey(f'second-payment-stale:{task.task_id.value}'), request.correlation_id))
    unit.commit()
    return False
