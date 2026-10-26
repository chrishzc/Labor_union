"""Read current Orders/Scheduling/Finance facts for group start-day notifications.

No business facts or provider effects are written here. The source worker and
webhook consumer respectively own their existing outer transactions.
"""
from datetime import date, datetime
import json

from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.line.service_start_day import (
    EVENT_CODE, EVENT_PREFIX, SOURCE_TYPE, ServiceStartDayCandidate, StartDayCaregiver,
)


class MySqlServiceStartDayRepository:
    def __init__(self, connection):
        self.connection = connection

    def find_due_candidates(self, target_date: date) -> tuple[ServiceStartDayCandidate, ...]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM orders WHERE actual_start_date=%s "
                           "AND status IN ('訂單成立','服務中') ORDER BY case_no", (target_date,))
            cases = tuple(row['case_no'] for row in cursor.fetchall())
        result = []
        for case_no in cases:
            candidate = self.current(case_no, target_date, lock=True)
            if candidate is not None and not self._already_delivered(case_no, target_date):
                result.append(candidate)
        return tuple(result)

    def current(self, case_no: str, service_date: date, *, lock=False):
        with self.connection.cursor() as cursor:
            # Match the existing Orders -> Scheduling/Finance lock order.
            cursor.execute("SELECT actual_start_date,status FROM orders WHERE case_no=%s"
                           + (' FOR UPDATE' if lock else ''), (case_no,))
            order = cursor.fetchone()
            if (not order or order['actual_start_date'] != service_date
                    or order['status'] not in ('訂單成立', '服務中')):
                return None
            cursor.execute("SELECT b.group_id,g.effective_generation_id FROM line_order_group_bindings b "
                           "JOIN scheduling_aggregates g ON g.case_no=b.case_no "
                           "WHERE b.case_no=%s AND b.binding_status IN ('bound','inviting','active','attention') "
                           "AND g.effective_generation_id IS NOT NULL" + (' FOR UPDATE' if lock else ''), (case_no,))
            group = cursor.fetchone()
            if not group or not group['group_id']:
                return None
            cursor.execute("SELECT DISTINCT a.staff_id,s.name FROM case_staff_assignments a "
                           "JOIN staff_schedule d ON d.assignment_id=a.id "
                           "JOIN staff s ON s.id=a.staff_id "
                           "WHERE a.case_no=%s AND a.generation_id=%s AND d.work_date=%s "
                           "AND d.effective_marker=1 AND d.is_work_day=1 ORDER BY a.staff_id"
                           + (' FOR UPDATE' if lock else ''),
                           (case_no, group['effective_generation_id'], service_date))
            caregivers = tuple(StartDayCaregiver(int(row['staff_id']), str(row['name'])) for row in cursor.fetchall())
            if not caregivers:
                return None
            cursor.execute("SELECT amount_due_ntd FROM client_obligations "
                           "WHERE case_no=%s AND obligation_type='first' AND direction='receivable_from_client' "
                           "AND status='open'" + (' FOR UPDATE' if lock else ''), (case_no,))
            amount = max(0, sum(int(row['amount_due_ntd']) for row in cursor.fetchall()))
        return ServiceStartDayCandidate(case_no, service_date, str(group['group_id']),
                                        int(group['effective_generation_id']), amount, caregivers)

    def _source(self, token):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT facts_snapshot FROM line_notification_source_events "
                           "WHERE source_domain='orders' AND event_code=%s AND source_event_identity=%s",
                           (EVENT_CODE, EVENT_PREFIX + token))
            row = cursor.fetchone()
        if not row:
            return None
        return json.loads(row['facts_snapshot']) if isinstance(row['facts_snapshot'], str) else row['facts_snapshot']

    def response_context(self, token, group_id, line_user_id):
        source = self._source(token)
        if not source or source['group_id'] != group_id:
            return None
        current = self.current(source['case_no'], date.fromisoformat(source['service_date']), lock=True)
        if (current is None or current.group_id != group_id
                or current.generation_id != source['generation_id']):
            return None
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT subject_reference FROM line_identity_role_bindings "
                           "WHERE line_user_id=%s AND subject_type='staff' AND binding_status='bound' FOR UPDATE",
                           (line_user_id,))
            binding = cursor.fetchone()
        if not binding or str(binding['subject_reference']) not in {str(item.staff_id) for item in current.caregivers}:
            return None
        return current

    def delivery_is_current(self, task, now: datetime):
        token = (task.request.source_aggregate_identity if task.request.source_aggregate_type != SOURCE_TYPE
                 else task.request.correlation_id.value.removeprefix('line-notification:' + EVENT_PREFIX))
        source = self._source(token)
        if source is None or task.request.recipient.recipient_type.value != 'group':
            return False
        day = date.fromisoformat(source['service_date'])
        current = self.current(source['case_no'], day, lock=True)
        if current is None or current.group_id != task.request.recipient.identity.value:
            return False
        if task.request.source_aggregate_type == 'order_service_start_day_response':
            return current.generation_id == source['generation_id']
        return now.astimezone(TAIPEI_TIME_ZONE).date() == day and current.facts() == {
            key: source[key] for key in current.facts()
        } and not self._already_delivered(current.case_no, day, excluding_task=task.task_id.value)

    def _already_delivered(self, case_no, day, *, excluding_task=0):
        with self.connection.cursor() as cursor:
            # A completed/uncertain delivery is not automatically repeated when
            # payment changes later that day. Stale unsent snapshots can be replaced.
            cursor.execute("SELECT 1 FROM line_notification_source_events s "
                           "JOIN line_notification_decisions d ON d.source_event_id=s.id "
                           "JOIN line_notification_intents i ON i.decision_id=d.id "
                           "JOIN line_delivery_tasks t ON t.id=i.delivery_task_id "
                           "WHERE s.event_code=%s AND s.source_aggregate_identity=%s "
                           "AND JSON_UNQUOTE(JSON_EXTRACT(s.facts_snapshot,'$.service_date'))=%s "
                           "AND t.id<>%s AND (i.intent_status='provider_accepted' "
                           "OR t.processing_status='sent' OR t.completed_attempts>0) LIMIT 1 FOR UPDATE",
                           (EVENT_CODE, case_no, day.isoformat(), excluding_task))
            return cursor.fetchone() is not None
