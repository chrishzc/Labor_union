"""Join typed Finance overdue facts with LINE-owned recipients and delivery history."""
from domains.line.delivery import LineRecipient, LineRecipientType
from domains.line.identities import LineDeliveryTaskId, LineUserId
from infrastructure.mysql.deposit_notification_repository import MySqlDepositNotificationRepository
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.line_repository_support import aware_utc
from infrastructure.mysql.overdue_payment_query_repository import MySqlOverduePaymentQueryRepository
from subsystems.client_finance.overdue_payment_query import OverduePaymentQueryPort
from subsystems.line.payment_overdue_reminders import (
    SOURCE_TYPE, CASE_SOURCE_TYPE, CaseReminderRecord, LastPaymentReminder, PaymentOverdueTodo, ReminderRecipient, payment_reference,
)


class MySqlPaymentOverdueReminderRepository:
    def __init__(self, connection):
        self.connection = connection
        self.payments: OverduePaymentQueryPort = MySqlOverduePaymentQueryRepository(connection)

    def case_facts(self, case_no):
        from infrastructure.mysql.client_payment_reminder_query_repository import MySqlClientPaymentReminderQueryRepository
        return MySqlClientPaymentReminderQueryRepository(self.connection).for_case(case_no)

    def history(self, case_no, stage):
        import json
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT t.id,t.processing_status,t.scheduled_at_utc,t.sent_at_utc,t.payload_snapshot, (SELECT a.actor_id FROM line_domain_audit_events a WHERE a.action='payment_overdue_reminder_queued' AND BINARY a.aggregate_type=BINARY t.source_aggregate_type AND BINARY a.aggregate_identity=BINARY CAST(t.id AS CHAR) ORDER BY a.id LIMIT 1) actor FROM line_delivery_tasks t "
                "WHERE (source_aggregate_type IN (%s,%s,%s,%s) AND BINARY source_aggregate_identity IN "
                "(SELECT BINARY obligation_identity FROM client_obligations WHERE case_no=%s AND obligation_type=%s) "
                "OR source_aggregate_type='client_deposit_reminder' AND %s='deposit' AND SUBSTRING_INDEX(source_aggregate_identity,':',1)=%s "
                "OR source_aggregate_type='client_second_payment_reminder' AND %s='second' AND source_aggregate_identity=%s) "
                "ORDER BY t.scheduled_at_utc DESC,t.id DESC", (SOURCE_TYPE,CASE_SOURCE_TYPE,'client_payment_initial_reminder',
                    'client_payment_automatic_followup',case_no,stage,stage,case_no,stage,case_no))
            rows = cursor.fetchall()
        result=[]
        for row in rows:
            payload=row['payload_snapshot']
            if isinstance(payload,str): payload=json.loads(payload)
            content=payload.get('text') if isinstance(payload,dict) and payload.get('type')=='text' else None
            result.append(CaseReminderRecord(int(row['id']),aware_utc(row['scheduled_at_utc']),
                aware_utc(row['sent_at_utc']) if row['sent_at_utc'] and row['processing_status']=='sent' else None,
                str(row['processing_status']),content,row['actor']))
        return tuple(result)

    def list(self, day, page, page_size):
        payments,total = self.payments.list(day,page,page_size)
        items = []
        for payment in payments:
            recipient = self.recipient(payment)
            pending = self.has_pending(payment.obligation_identity)
            reason = None if recipient else '尚未綁定客戶 LINE'
            if recipient and pending:
                reason = '本期款項已有寄送工作，請先確認原工作結果。'
            items.append(PaymentOverdueTodo(payment,(day-payment.due_date).days,
                '客戶私人聊天室',bool(recipient) and not pending,
                reason,self.last(payment.obligation_identity)))
        return tuple(items),total

    def payment(self, identity, *, lock=False):
        return self.payments.get(identity,lock=lock)

    def recipient(self, payment, *, lock=False):
        user = MySqlDepositNotificationRepository(self.connection).customer_line_user_id(payment.case_no,lock=lock)
        return ReminderRecipient(LineRecipient(LineRecipientType.USER,LineUserId(user)),0) if user else None

    def existing(self, key):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT id FROM line_delivery_tasks WHERE idempotency_key=%s FOR UPDATE',(key.value,))
            row = cursor.fetchone()
        return MySqlLineDeliveryTaskRepository(self.connection).get(LineDeliveryTaskId(int(row['id']))) if row else None

    def has_pending(self, identity, *, lock=False):
        from infrastructure.mysql.payment_reminder_notification_repository import MySqlPaymentReminderNotificationRepository
        return MySqlPaymentReminderNotificationRepository(self.connection).pending(identity,lock=lock)

    def last(self, identity):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT scheduled_at_utc,processing_status FROM line_delivery_tasks '
                'WHERE source_aggregate_type IN (%s,%s,%s,%s) AND source_aggregate_identity=%s ORDER BY id DESC LIMIT 1',
                (SOURCE_TYPE,CASE_SOURCE_TYPE,'client_payment_initial_reminder','client_payment_automatic_followup',identity))
            row = cursor.fetchone()
        return LastPaymentReminder(aware_utc(row['scheduled_at_utc']),str(row['processing_status'])) if row else None

    def delivery_is_current(self, task, now):
        payment = self.payment(task.request.source_aggregate_identity,lock=True)
        from shared_kernel.clock import TAIPEI_TIME_ZONE
        if payment is None or payment.remaining_amount_ntd <= 0 or (task.request.source_aggregate_type != CASE_SOURCE_TYPE and not payment.overdue_on(now.astimezone(TAIPEI_TIME_ZONE).date())):
            return False
        if task.request.source_aggregate_type == CASE_SOURCE_TYPE:
            matches=[row for row in self.case_facts(payment.case_no) if row.payment.payment_stage==payment.payment_stage]
            if len(matches)!=1 or not matches[0].contract_completed or matches[0].payment!=payment:
                return False
        recipient = self.recipient(payment,lock=True)
        # The queued payload is immutable display copy. Freshness belongs to its
        # Finance provenance and recipient, not equality with default wording.
        return bool(recipient and recipient.recipient == task.request.recipient
            and task.request.correlation_id.value == payment_reference(payment)+f':{recipient.binding_version}')
