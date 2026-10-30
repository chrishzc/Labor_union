"""Join typed Finance overdue facts with LINE-owned recipients and delivery history."""
from domains.line.delivery import LineRecipient, LineRecipientType
from domains.line.identities import LineDeliveryTaskId, LineUserId
from infrastructure.mysql.deposit_notification_repository import MySqlDepositNotificationRepository
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.line_repository_support import aware_utc
from infrastructure.mysql.overdue_payment_query_repository import MySqlOverduePaymentQueryRepository
from subsystems.client_finance.overdue_payment_query import OverduePaymentQueryPort
from subsystems.line.payment_overdue_reminders import (
    SOURCE_TYPE, LastPaymentReminder, PaymentOverdueTodo, ReminderRecipient, payment_reference,
)


class MySqlPaymentOverdueReminderRepository:
    def __init__(self, connection):
        self.connection = connection
        self.payments: OverduePaymentQueryPort = MySqlOverduePaymentQueryRepository(connection)

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
                'WHERE source_aggregate_type IN (%s,%s,%s) AND source_aggregate_identity=%s ORDER BY id DESC LIMIT 1',
                (SOURCE_TYPE,'client_payment_initial_reminder','client_payment_automatic_followup',identity))
            row = cursor.fetchone()
        return LastPaymentReminder(aware_utc(row['scheduled_at_utc']),str(row['processing_status'])) if row else None

    def delivery_is_current(self, task, now):
        payment = self.payment(task.request.source_aggregate_identity,lock=True)
        from shared_kernel.clock import TAIPEI_TIME_ZONE
        if payment is None or not payment.overdue_on(now.astimezone(TAIPEI_TIME_ZONE).date()):
            return False
        recipient = self.recipient(payment,lock=True)
        # The queued payload is immutable display copy. Freshness belongs to its
        # Finance provenance and recipient, not equality with default wording.
        return bool(recipient and recipient.recipient == task.request.recipient
            and task.request.correlation_id.value == payment_reference(payment)+f':{recipient.binding_version}')
