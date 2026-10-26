"""Read-only second-payment eligibility and committed settlement sources.

Locks join the source/delivery worker's outer UoW. No Finance root or outbox
processing status is changed. Missing groups use existing LINE-006 staff todos.
"""
from dataclasses import asdict
import json

from infrastructure.mysql.second_payment_query_repository import MySqlSecondPaymentQueryRepository
from subsystems.client_finance.second_payment_query import SecondPaymentQueryPort
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.line.second_payment_notifications import SecondPaymentNotification, REMINDER, SETTLED, DUE_EVENT, SETTLED_EVENT


class MySqlSecondPaymentNotificationRepository:
    def __init__(self, connection):
        self.connection = connection
        self.payments: SecondPaymentQueryPort = MySqlSecondPaymentQueryRepository(connection)

    def current(self, case_no, *, lock=False):
        suffix = ' FOR UPDATE' if lock else ''
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT status FROM orders WHERE case_no=%s' + suffix, (case_no,))
            order = cursor.fetchone()
            if not order or order['status'] not in ('洽談中', '訂單成立', '服務中', '訂單完成'):
                return None
        financial = self.payments.get(case_no, lock=lock)
        if financial is None:
            return None
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT group_id,aggregate_version FROM line_order_group_bindings WHERE case_no=%s '
                           "AND binding_status IN ('bound','inviting','active','attention')" + suffix, (case_no,))
            group = cursor.fetchone()
        return SecondPaymentNotification(**asdict(financial), group_id=str(group['group_id']) if group and group['group_id'] else None,
                                         group_version=int(group['aggregate_version']) if group else 0)

    def find_due_candidates(self, target_date):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT case_no FROM client_payment_terms WHERE second_payment_due_date=%s ORDER BY case_no', (target_date,))
            cases = tuple(row['case_no'] for row in cursor.fetchall())
        candidates = []
        for case_no in cases:
            current = self.current(case_no, lock=True)
            if (current and current.due_date == target_date and current.remaining_amount > 0
                    and not self._attempted(current)):
                candidates.append(current)
        return tuple(candidates)

    def find_settlement_candidates(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id,case_no,payload_snapshot FROM client_finance_outbox WHERE intent_type='projection_refresh' "
                           "AND JSON_EXTRACT(payload_snapshot,'$.line_second_payment_notification')=TRUE ORDER BY id")
            events = tuple(cursor.fetchall())
        candidates = []
        for event in events:
            payload = _object(event['payload_snapshot'])
            current = self.settlement(event['case_no'], payload['settlement_identity'], lock=True)
            if current and not self._attempted(current):
                candidates.append(current)
        return tuple(candidates)

    def settlement(self, case_no, identity, *, lock=False):
        current = self.current(case_no, lock=lock)
        if current is None:
            return None
        financial = self.payments.settlement(case_no, identity, lock=lock)
        return None if financial is None else SecondPaymentNotification(**asdict(financial), group_id=current.group_id,
                                                                        group_version=current.group_version)

    def _attempted(self, payment, *, excluding_task=0):
        paid = payment.settlement_identity is not None
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM line_notification_source_events s '
                           'JOIN line_notification_decisions d ON d.source_event_id=s.id '
                           'JOIN line_notification_intents i ON i.decision_id=d.id '
                           'JOIN line_delivery_tasks t ON t.id=i.delivery_task_id '
                           'WHERE s.event_code=%s AND s.source_aggregate_identity=%s AND t.id<>%s '
                           "AND JSON_UNQUOTE(JSON_EXTRACT(s.facts_snapshot,%s))=%s "
                           "AND (t.processing_status='sent' OR t.completed_attempts>0 OR i.intent_status='provider_accepted') LIMIT 1 FOR UPDATE",
                           (SETTLED_EVENT if paid else DUE_EVENT, payment.case_no, excluding_task,
                            '$.settlement_identity' if paid else '$.second_payment_due_date',
                            payment.settlement_identity if paid else payment.due_date.isoformat()))
            return cursor.fetchone() is not None

    def delivery_is_current(self, task, now):
        request = task.request
        identity = request.correlation_id.value.removeprefix('line-notification:')
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT facts_snapshot,event_code FROM line_notification_source_events '
                           "WHERE source_domain='client_finance' AND source_event_identity=%s AND event_code=%s",
                           (identity, SETTLED_EVENT if request.source_aggregate_type==SETTLED else DUE_EVENT))
            source = cursor.fetchone()
        if not source or request.recipient.recipient_type.value != 'group':
            return False
        facts = _object(source['facts_snapshot'])
        if request.source_aggregate_type == SETTLED:
            current = self.settlement(facts['case_no'], facts['settlement_identity'], lock=True)
        else:
            current = self.current(facts['case_no'], lock=True)
            if not current or current.remaining_amount <= 0 or current.due_date != now.astimezone(TAIPEI_TIME_ZONE).date():
                return False
        return bool(current and current.group_id == request.recipient.identity.value
                    and current.facts() == {key:facts.get(key) for key in current.facts()}
                    and not self._attempted(current, excluding_task=task.task_id.value))

    def source_is_current(self, facts, event_code, *, lock=False):
        if event_code == SETTLED_EVENT:
            current = self.settlement(facts['case_no'], facts['settlement_identity'], lock=lock)
        else:
            current = self.current(facts['case_no'], lock=lock)
            if not current or current.remaining_amount <= 0:
                return False
        return bool(current and current.facts() == {key:facts.get(key) for key in current.facts()})


def _object(value):
    return json.loads(value) if isinstance(value, str) else value
