"""Read committed Orders completion evidence; never complete an order or publish menus."""

import json

from subsystems.line.service_completion_notifications import ServiceCompletionNotification, EVENT_CODE


class MySqlServiceCompletionNotificationRepository:
    def __init__(self, connection):
        self.connection = connection

    def find_candidates(self):
        with self.connection.cursor() as c:
            # Only newly produced, explicitly marked completions; no historical backfill.
            c.execute("SELECT id FROM orders_domain_outbox WHERE intent_type='lifecycle_projection_changed' "
                "AND JSON_EXTRACT(payload_snapshot,'$.line_service_completion_notification')=TRUE ORDER BY id")
            identities = tuple(row['id'] for row in c.fetchall())
        return tuple(current for identity in identities
            if (current := self.current(identity, lock=True)) is not None and not self._attempted(current))

    def current(self, outbox_id, *, lock=False):
        suffix = ' FOR UPDATE' if lock else ''
        with self.connection.cursor() as c:
            c.execute('SELECT outbox.case_no,outbox.lifecycle_event_id,outbox.payload_snapshot '
                'FROM orders_domain_outbox outbox JOIN orders o ON o.case_no=outbox.case_no '
                'JOIN order_service_data_locks service_lock ON service_lock.case_no=o.case_no '
                "AND service_lock.lifecycle_event_id=outbox.lifecycle_event_id WHERE outbox.id=%s "
                "AND o.status='訂單完成' AND outbox.intent_type='lifecycle_projection_changed'"+suffix,(outbox_id,))
            row = c.fetchone()
            if not row:
                return None
            payload = _object(row['payload_snapshot'])
            if (payload.get('line_service_completion_notification') is not True
                    or payload.get('event_type') != 'case_terminal_closure'
                    or payload.get('terminal_kind') != 'completion'):
                return None
            c.execute('SELECT group_id,aggregate_version FROM line_order_group_bindings WHERE case_no=%s '
                "AND binding_status IN ('bound','inviting','active','attention')"+suffix,(row['case_no'],))
            group = c.fetchone()
        return ServiceCompletionNotification(row['case_no'],payload['source_event_identity'],
            int(row['lifecycle_event_id']),int(payload['resulting_order_version']),
            str(group['group_id']) if group and group['group_id'] else None,
            int(group['aggregate_version']) if group else 0)

    def _attempted(self, candidate, excluding_task=0):
        with self.connection.cursor() as c:
            c.execute('SELECT 1 FROM line_notification_source_events s '
                'JOIN line_notification_decisions d ON d.source_event_id=s.id '
                'JOIN line_notification_intents i ON i.decision_id=d.id '
                'JOIN line_delivery_tasks t ON t.id=i.delivery_task_id '
                'WHERE s.event_code=%s AND s.source_aggregate_identity=%s AND t.id<>%s '
                "AND JSON_UNQUOTE(JSON_EXTRACT(s.facts_snapshot,'$.completion_identity'))=%s "
                "AND (t.processing_status='sent' OR t.completed_attempts>0 OR i.intent_status='provider_accepted') LIMIT 1 FOR UPDATE",
                (EVENT_CODE,candidate.case_no,excluding_task,candidate.completion_identity))
            return c.fetchone() is not None

    def source_is_current(self, facts, *, lock=False):
        with self.connection.cursor() as c:
            c.execute('SELECT id FROM orders_domain_outbox WHERE case_no=%s AND lifecycle_event_id=%s '
                "AND intent_type='lifecycle_projection_changed' ORDER BY id LIMIT 1",(facts['case_no'],facts['lifecycle_event_id']))
            source = c.fetchone()
        current = self.current(source['id'],lock=lock) if source else None
        return current if current and current.facts() == facts else None

    def delivery_is_current(self, task):
        if task.request.recipient.recipient_type.value != 'group':
            return False
        identity = task.request.correlation_id.value.removeprefix('line-notification:')
        with self.connection.cursor() as c:
            c.execute('SELECT facts_snapshot FROM line_notification_source_events '
                "WHERE source_domain='orders' AND source_event_identity=%s AND event_code=%s",(identity,EVENT_CODE))
            source = c.fetchone()
        current = self.source_is_current(_object(source['facts_snapshot']),lock=True) if source else None
        return bool(current and current.group_id == task.request.recipient.identity.value
            and not self._attempted(current,task.task_id.value))


def _object(value):
    return json.loads(value) if isinstance(value,str) else value
