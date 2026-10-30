"""LINE history and verified private replies; no account or webhook mutations."""
from domains.line.delivery import LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from infrastructure.mysql.client_payment_reminder_query_repository import MySqlClientPaymentReminderQueryRepository
from infrastructure.mysql.deposit_notification_repository import MySqlDepositNotificationRepository
from infrastructure.mysql.line_repository_support import aware_utc, database_utc
from subsystems.line.payment_overdue_reminders import ReminderRecipient
from subsystems.line.payment_reminder_notifications import INITIAL, FOLLOWUP, OriginalPaymentReminder


class MySqlPaymentReminderNotificationRepository:
    def __init__(self, connection):
        self.connection=connection
        self.payments=MySqlClientPaymentReminderQueryRepository(connection)

    def candidates(self, day, after='', limit=100):
        return self.payments.candidates(day,after,limit)

    def payment(self, identity, *, lock=False):
        return self.payments.get(identity,lock=lock)

    def recipient(self, case_no, *, lock=False):
        user=MySqlDepositNotificationRepository(self.connection).customer_line_user_id(case_no,lock=lock)
        return ReminderRecipient(LineRecipient(LineRecipientType.USER,LineUserId(user)),0) if user else None

    def original(self, payment, *, lock=False):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT id,processing_status,sent_at_utc,recipient_identity FROM line_delivery_tasks '
                "WHERE (source_aggregate_type=%s AND source_aggregate_identity=%s "
                "OR source_aggregate_type='client_deposit_reminder' AND %s='deposit' "
                "AND SUBSTRING_INDEX(source_aggregate_identity,':',1)=%s "
                "OR source_aggregate_type='client_second_payment_reminder' AND %s='second' AND source_aggregate_identity=%s) "
                "AND (processing_status<>'cancelled' OR completed_attempts>0) "
                "ORDER BY CASE WHEN processing_status='sent' THEN 0 ELSE 1 END,id LIMIT 1"+(' FOR UPDATE' if lock else ''),
                (INITIAL,payment.obligation_identity,payment.payment_stage,payment.case_no,payment.payment_stage,payment.case_no))
            row=cursor.fetchone()
        return OriginalPaymentReminder(int(row['id']),str(row['processing_status']),aware_utc(row['sent_at_utc']) if row['sent_at_utc'] else None,str(row['recipient_identity'])) if row else None

    def has_followup(self, identity):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM line_delivery_tasks WHERE source_aggregate_type=%s '
                'AND source_aggregate_identity=%s LIMIT 1 FOR UPDATE',(FOLLOWUP,identity))
            return cursor.fetchone() is not None

    def replied(self, user_id, since):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM line_inbox_events WHERE source_type='user' "
                "AND source_user_id=%s AND event_type IN ('message','postback') "
                'AND occurred_at_utc>=%s LIMIT 1 FOR UPDATE',(user_id,database_utc(since)))
            return cursor.fetchone() is not None

    def pending(self, identity, *, lock=True):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM line_delivery_tasks WHERE (source_aggregate_identity=%s '
                'AND source_aggregate_type IN (%s,%s,%s) '
                "OR source_aggregate_type='client_deposit_reminder' AND SUBSTRING_INDEX(source_aggregate_identity,':',1)="
                "(SELECT case_no FROM client_obligations WHERE obligation_identity=%s AND obligation_type='deposit')) "
                "AND processing_status IN ('pending','processing','retryable_failed') LIMIT 1"+(' FOR UPDATE' if lock else ''),
                (identity,INITIAL,FOLLOWUP,'manual_payment_overdue_reminder',identity))
            return cursor.fetchone() is not None
