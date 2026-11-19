"""LINE-owned current handling decisions shared by delivery and failure views."""
from dataclasses import dataclass
from typing import Literal

from domains.line.delivery import LineDeliveryStatus
from subsystems.line.capabilities import LineCapability
from subsystems.line.delivery_contracts import (
    REPLY_ONLY_WEBHOOK_SOURCE, RETIRED_CONTRACT_DELIVERY_SOURCES,
    RETIRED_PAYMENT_RECEIPT_DELIVERY_SOURCES,
    retired_delivery_reason,
)
from subsystems.line.notification_failure_current_fact import build_line_notification_failure_recheck_intent


@dataclass(frozen=True, slots=True)
class NotificationHandling:
    target_kind: Literal['delivery_task', 'notification_failure']
    target_identity: str
    needs_attention: bool
    allowed_actions: tuple[Literal['retry', 'cancel', 'replay', 'close'], ...]
    blocked_reason: str | None = None


def delivery_handling(task, actor, *, request, target=None):
    control = LineCapability.TASK_CONTROL.value in actor.permission_scope
    uncertain = task.error_code == 'line_reply_outcome_uncertain'
    active = task.status not in (LineDeliveryStatus.SENT, LineDeliveryStatus.CANCELLED)
    control = control and (target is None or LineCapability.CONFIG_MANAGE.value in actor.permission_scope)
    blocked = ('寄送結果尚未確認，請先核對結果。' if uncertain else
               '工作正在寄送，請等待結果確認後重新核對。' if task.status is LineDeliveryStatus.PROCESSING else
               '目前帳號沒有處理寄送工作的權限。' if not control else None)
    actions = []
    retired = task.source_aggregate_type in (*RETIRED_CONTRACT_DELIVERY_SOURCES,
        *RETIRED_PAYMENT_RECEIPT_DELIVERY_SOURCES, REPLY_ONLY_WEBHOOK_SOURCE,
        'customer_service_ticket', 'runtime_health_event') or (
            retired_delivery_reason(request) is not None)
    if not blocked and active:
        if task.status in (LineDeliveryStatus.FAILED, LineDeliveryStatus.RETRYABLE_FAILED) and not retired:
            actions.append('retry')
        actions.append('close' if target is not None else 'cancel')
    return NotificationHandling('notification_failure' if target else 'delivery_task',
        target or str(task.task_id.value), active and task.status is LineDeliveryStatus.FAILED,
        tuple(actions), blocked)


def current_failure_target(unit, task_id):
    """Resolve the canonical current issue through its typed owner scope."""
    matches = set()
    for target in unit.notification_rules.line006_recheck_targets_for_delivery_task(task_id):
        from subsystems.line.notification_failure_current_fact import LineNotificationFailureCurrentFactQuery
        current = unit.notification_rules.current_failure_fact(
            LineNotificationFailureCurrentFactQuery(target.case_no, target.notification_reason))
        if not current.authoritative_complete:
            raise RuntimeError('line_failure_task_readback_incomplete')
        if not current.predicate_active or task_id not in current.related_task_ids:
            continue
        scope = build_line_notification_failure_recheck_intent(current, cause_identity='handling-query').scope
        for projection in unit.anomaly_rechecks.list_current(scope):
            candidate = projection.candidate
            if candidate.subject_identity == {'case_no': target.case_no, 'notification_reason': target.notification_reason.value}:
                matches.add(candidate.issue_key)
    if len(matches) > 1:
        raise RuntimeError('line_failure_task_target_ambiguous')
    return next(iter(matches), None)


def failure_handling(current, tasks, actor, issue_key, *, can_replay):
    manage = LineCapability.CONFIG_MANAGE.value in actor.permission_scope
    control = not tasks or LineCapability.TASK_CONTROL.value in actor.permission_scope
    blocked = ('原通知資料尚未完整核對，請稍後重試。' if not current.authoritative_complete else
               '有工作正在寄送或結果未確認，請先核對寄送結果。'
               if any(t.status is LineDeliveryStatus.PROCESSING or t.error_code == 'line_reply_outcome_uncertain' for t in tasks) else
               '目前帳號沒有結清此範圍所需的權限。' if not manage or not control else None)
    actions = []
    if current.predicate_active and not blocked:
        if can_replay:
            actions.append('replay')
        actions.append('close')
    return NotificationHandling('notification_failure', issue_key, current.predicate_active, tuple(actions), blocked)
