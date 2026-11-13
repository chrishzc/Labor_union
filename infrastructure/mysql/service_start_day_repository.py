"""
File: service_start_day_repository.py
Description: 唯讀驗證舊開工詢問按鈕的 Reply-only 回覆現行性；不再產生 Push 來源。
"""
from datetime import date, datetime
import json

from subsystems.line.service_start_day import (
    EVENT_CODE, EVENT_PREFIX, ServiceStartDayCandidate, StartDayCaregiver, start_day_reply_token,
)


class MySqlServiceStartDayRepository:
    def __init__(self, connection):
        self.connection = connection

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
            # Payment reminders have their own private-customer workflow. This
            # source now asks only the assigned caregivers about service status.
            amount = 0
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
        # 只驗證舊按鈕 Reply ack；開工詢問 Push 已退役，由 provider 前守門取消。
        token = start_day_reply_token(task)
        source = self._source(token) if token is not None else None
        if source is None or task.request.recipient.recipient_type.value != 'group':
            return False
        current = self.current(source['case_no'], date.fromisoformat(source['service_date']), lock=True)
        return (current is not None and current.group_id == task.request.recipient.identity.value
                and current.generation_id == source['generation_id'])