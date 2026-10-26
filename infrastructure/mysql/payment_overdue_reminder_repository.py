"""Join typed Finance overdue facts with LINE-owned recipients and delivery history."""
from domains.line.delivery import LineRecipient, LineRecipientType
from domains.line.identities import LineDeliveryTaskId, LineGroupId, LineUserId
from infrastructure.mysql.deposit_notification_repository import MySqlDepositNotificationRepository
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.line_repository_support import aware_utc
from infrastructure.mysql.overdue_payment_query_repository import MySqlOverduePaymentQueryRepository
from subsystems.client_finance.overdue_payment_query import OverduePaymentQueryPort
from subsystems.line.payment_overdue_reminders import (
    SOURCE_TYPE, LastPaymentReminder, PaymentOverdueTodo, ReminderRecipient, payment_reference, reminder_text,
)
import json


class MySqlPaymentOverdueReminderRepository:
    def __init__(self, connection):
        self.connection = connection
        self.payments: OverduePaymentQueryPort = MySqlOverduePaymentQueryRepository(connection)

    def list(self, day, page, page_size):
        payments,total = self.payments.list(day,page,page_size)
        items = []
        for payment in payments:
            recipient = self.recipient(payment)
            deposit = payment.payment_stage == 'deposit'
            items.append(PaymentOverdueTodo(payment,(day-payment.due_date).days,
                '客戶私人聊天室' if deposit else f'案件 {payment.case_no} 群組',bool(recipient),
                None if recipient else '尚未綁定客戶 LINE' if deposit else '尚無可用案件群組',self.last(payment.obligation_identity)))
        return tuple(items),total

    def payment(self, identity, *, lock=False):
        return self.payments.get(identity,lock=lock)

    def recipient(self, payment, *, lock=False):
        if payment.payment_stage == 'deposit':
            user = MySqlDepositNotificationRepository(self.connection).customer_line_user_id(payment.case_no,lock=lock)
            return ReminderRecipient(LineRecipient(LineRecipientType.USER,LineUserId(user)),0) if user else None
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT group_id,aggregate_version FROM line_order_group_bindings WHERE case_no=%s '
                "AND binding_status IN ('bound','inviting','active','attention')"+(' FOR UPDATE' if lock else ''),(payment.case_no,))
            row = cursor.fetchone()
        return (ReminderRecipient(LineRecipient(LineRecipientType.GROUP,LineGroupId(str(row['group_id']))),int(row['aggregate_version']))
                if row and row['group_id'] else None)

    def existing(self, key):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT id FROM line_delivery_tasks WHERE idempotency_key=%s FOR UPDATE',(key.value,))
            row = cursor.fetchone()
        return MySqlLineDeliveryTaskRepository(self.connection).get(LineDeliveryTaskId(int(row['id']))) if row else None

    def last(self, identity):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT scheduled_at_utc,processing_status FROM line_delivery_tasks '
                'WHERE source_aggregate_type=%s AND source_aggregate_identity=%s ORDER BY id DESC LIMIT 1',(SOURCE_TYPE,identity))
            row = cursor.fetchone()
        return LastPaymentReminder(aware_utc(row['scheduled_at_utc']),str(row['processing_status'])) if row else None

    def delivery_is_current(self, task, now):
        payment = self.payment(task.request.source_aggregate_identity,lock=True)
        from shared_kernel.clock import TAIPEI_TIME_ZONE
        if payment is None or not payment.overdue_on(now.astimezone(TAIPEI_TIME_ZONE).date()):
            return False
        recipient = self.recipient(payment,lock=True)
        return bool(recipient and recipient.recipient == task.request.recipient
            and task.request.correlation_id.value == payment_reference(payment)+f':{recipient.binding_version}'
            and json.loads(task.request.payload_json) == {'type':'text','text':reminder_text(payment)})
