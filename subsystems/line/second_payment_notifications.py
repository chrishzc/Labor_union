"""第二期款群組通知已退役；僅保留 provider 前守門，取消殘留的舊群組工作。"""
from datetime import datetime

REMINDER = 'client_second_payment_reminder'
SETTLED = 'client_second_payment_settled'
_RETIRED_PREFIX = 'line-notification:order-second-payment-reminder:'


def second_payment_delivery_is_current(unit, task, now: datetime):
    from shared_kernel.identities import ActorContext, IdempotencyKey
    from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand

    request = task.request
    if not (request.correlation_id.value.startswith(_RETIRED_PREFIX)
            or request.source_aggregate_type in (REMINDER, SETTLED)):
        return True
    unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id, ActorContext('line-second-payment-worker'),
        IdempotencyKey(f'second-payment-stale:{task.task_id.value}'), request.correlation_id))
    unit.commit()
    return False