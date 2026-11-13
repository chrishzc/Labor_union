"""結案問卷群組邀請已退役；僅保留 provider 前守門，取消殘留的舊群組工作。"""

SOURCE_TYPE = 'order_service_completion'


def service_completion_delivery_is_current(unit, task):
    if task.request.source_aggregate_type != SOURCE_TYPE:
        return True
    from shared_kernel.identities import ActorContext, IdempotencyKey
    from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
    unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,
        ActorContext('line-service-completion'), IdempotencyKey(f'completion-stale:{task.task_id.value}'),
        task.request.correlation_id))
    unit.commit()
    return False