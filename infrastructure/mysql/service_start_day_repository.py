"""
File: service_start_day_repository.py
Description: 讀取開工日群組、排班及第一期款資料，驗證問候與回覆的對象。
"""
from datetime import date, datetime
from hashlib import sha256

from domains.line.delivery import LineMessageKind, LineRecipientType
from infrastructure.mysql.client_payment_reminder_query_repository import MySqlClientPaymentReminderQueryRepository
from infrastructure.mysql.order_notification_continuation_query_repository import notification_continuation_eligible_sql
from infrastructure.mysql.deposit_notification_repository import MySqlDepositNotificationRepository
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.line.service_start_day import (
    GREETING_SOURCE, ServiceStartDayCandidate, StartDayCaregiver, greeting_reference,
)


class MySqlServiceStartDayRepository:
    def __init__(self, connection):
        self.connection = connection

    def due_cases(self, day, after='', limit=100):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT o.case_no FROM orders o WHERE o.actual_start_date=%s AND o.case_no>%s "
                           "AND o.status IN ('訂單成立','服務中') AND "+notification_continuation_eligible_sql('o')+
                           " ORDER BY o.case_no LIMIT %s", (day, after, limit))
            return tuple(str(row['case_no']) for row in cursor.fetchall())

    def has_missing_group(self, case_no, day):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM orders o WHERE o.case_no=%s AND o.actual_start_date=%s "
                           "AND o.status IN ('訂單成立','服務中') AND "+notification_continuation_eligible_sql('o')+' '+
                           "AND NOT EXISTS (SELECT 1 FROM line_order_group_bindings b WHERE b.case_no=o.case_no "
                           "AND b.binding_status IN ('bound','inviting','active','attention') AND b.group_id IS NOT NULL)",
                           (case_no, day))
            return cursor.fetchone() is not None

    def first_payment(self, case_no):
        payments = MySqlClientPaymentReminderQueryRepository(self.connection)
        rows = [row for row in payments.for_case(case_no) if row.payment.payment_stage == 'first']
        if len(rows) != 1:
            return None
        facts = payments.get(rows[0].payment.obligation_identity, lock=True)
        if (facts is None or facts.payment.remaining_amount_ntd <= 0
                or not facts.notification_continuation.allows_automatic_payment(facts.payment.due_date)):
            return None
        return facts.payment

    def has_greeting(self, case_no, day):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM line_delivery_tasks WHERE source_aggregate_type=%s "
                           "AND source_aggregate_identity=%s AND correlation_id LIKE %s "
                           "AND (processing_status<>'cancelled' OR completed_attempts>0) LIMIT 1 FOR UPDATE",
                           (GREETING_SOURCE, case_no, f'opening-greeting:{day.isoformat()}:%'))
            if cursor.fetchone() is not None:
                return True
            # An opening notice sent or already attempted before the rollout is already accounted for.
            cursor.execute("SELECT 1 FROM line_delivery_tasks t JOIN client_obligations o "
                           "ON o.obligation_identity=t.source_aggregate_identity "
                           "WHERE t.source_aggregate_type='client_payment_initial_reminder' "
                           "AND o.case_no=%s AND o.obligation_type='first' AND t.recipient_type='group' "
                           "AND t.correlation_id LIKE %s AND (t.completed_attempts>0 OR t.processing_status='sent') "
                           "LIMIT 1 FOR UPDATE", (case_no, f'%:{day.isoformat()}'))
            return cursor.fetchone() is not None

    def current(self, case_no: str, service_date: date, *, lock=False):
        with self.connection.cursor() as cursor:
            # Match the existing Orders -> Scheduling/Finance lock order.
            cursor.execute("SELECT o.actual_start_date,o.status FROM orders o WHERE o.case_no=%s AND "
                           + notification_continuation_eligible_sql('o')
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
            # Opening notices read Finance separately.
            amount = 0
        return ServiceStartDayCandidate(case_no, service_date, str(group['group_id']),
                                        int(group['effective_generation_id']), amount, caregivers)

    def payment_reply_context(self, group_id, day, line_user_id):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT b.case_no,o.actual_start_date FROM line_order_group_bindings b "
                           "JOIN orders o ON o.case_no=b.case_no WHERE b.group_id=%s", (group_id,))
            binding = cursor.fetchone()
        if not binding:
            return None
        service_date = binding['actual_start_date']
        if service_date is None or service_date > day:
            return None
        current = self.current(binding['case_no'], service_date, lock=True)
        if current is None or current.group_id != group_id:
            return None
        first = self.first_payment(current.case_no)
        if first is None:
            return None
        payment_key = sha256(first.obligation_identity.encode()).hexdigest()
        with self.connection.cursor() as cursor:
            pattern = f'opening-greeting:{service_date.isoformat()}:{payment_key}:%'
            cursor.execute("SELECT id FROM line_delivery_tasks WHERE source_aggregate_type=%s "
                           "AND source_aggregate_identity=%s AND recipient_identity=%s AND correlation_id LIKE %s "
                           "AND processing_status='sent' ORDER BY id LIMIT 1 FOR UPDATE",
                           (GREETING_SOURCE, current.case_no, group_id, pattern))
            task = cursor.fetchone()
        if not task:
            return None
        customer = MySqlDepositNotificationRepository(self.connection).customer_line_user_id(current.case_no, lock=True)
        return (current, int(task['id'])) if customer == line_user_id else None

    def delivery_is_current(self, task, now: datetime):
        request = task.request
        if request.recipient.recipient_type is not LineRecipientType.GROUP or request.message_kind is not LineMessageKind.TEXT:
            return False
        day = now.astimezone(TAIPEI_TIME_ZONE).date()
        current = self.current(request.source_aggregate_identity, day, lock=True)
        return bool(current and current.group_id == request.recipient.identity.value
                    and greeting_reference(current, self.first_payment(current.case_no)) == request.correlation_id.value)
