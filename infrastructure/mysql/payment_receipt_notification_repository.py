"""Read marked committed settlements using existing Finance queries and LINE history."""
import json
from infrastructure.mysql.deposit_payment_query_repository import MySqlDepositPaymentQueryRepository
from infrastructure.mysql.deposit_notification_repository import MySqlDepositNotificationRepository
from infrastructure.mysql.second_payment_query_repository import MySqlSecondPaymentQueryRepository
from subsystems.line.payment_receipt_notifications import MANUAL_RECEIPT,PaymentReceiptCandidate,PaymentReceiptHistory


class MySqlPaymentReceiptNotificationRepository:
    def __init__(self,connection): self.connection=connection

    def candidates(self,after=0,limit=100):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id,case_no,intent_type,payload_snapshot FROM client_finance_outbox WHERE id>%s AND ("
                "intent_type='orders_deposit_reconciled' AND JSON_EXTRACT(payload_snapshot,'$.line_deposit_notification')=TRUE OR "
                "intent_type='projection_refresh' AND JSON_EXTRACT(payload_snapshot,'$.line_second_payment_notification')=TRUE) "
                'ORDER BY id LIMIT %s',(after,limit))
            return tuple(PaymentReceiptCandidate(int(row['id']),str(row['case_no']),
                'deposit' if row['intent_type']=='orders_deposit_reconciled' else 'second',
                str(_object(row['payload_snapshot'])['settlement_identity'])) for row in cursor.fetchall())

    def payment(self,case_no,stage,identity,*,lock=False):
        if stage not in ('deposit','second'): return None
        suffix=' FOR UPDATE' if lock else ''
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s AND status IN ('洽談中','訂單成立','服務中','訂單完成')"+suffix,(case_no,))
            if not cursor.fetchone(): return None
            if lock:
                cursor.execute('SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE',(case_no,));cursor.fetchone()
            flag='line_deposit_notification' if stage=='deposit' else 'line_second_payment_notification'
            cursor.execute("SELECT id FROM client_finance_outbox WHERE case_no=%s AND intent_type=%s "
                f"AND JSON_EXTRACT(payload_snapshot,'$.{flag}')=TRUE "
                "AND JSON_UNQUOTE(JSON_EXTRACT(payload_snapshot,'$.settlement_identity'))=%s LIMIT 1"+suffix,
                (case_no,'orders_deposit_reconciled' if stage=='deposit' else 'projection_refresh',identity))
            if not cursor.fetchone(): return None
        if stage=='second': return MySqlSecondPaymentQueryRepository(self.connection).settlement(case_no,identity,lock=lock)
        payment=MySqlDepositPaymentQueryRepository(self.connection).get(case_no,lock=lock)
        return payment if payment and payment.settlement_identity==identity else None

    def recipient(self,case_no,*,lock=False):
        return MySqlDepositNotificationRepository(self.connection).customer_line_user_id(case_no,lock=lock)

    def automatic_receipt(self,task):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM line_notification_source_events WHERE source_event_identity=%s "
                "AND event_code='deposit_confirmed' LIMIT 1",(task.request.correlation_id.value.removeprefix('line-notification:'),))
            return cursor.fetchone() is not None

    def history(self,payment,*,lock=False):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT processing_status status,completed_attempts attempts FROM line_delivery_tasks t WHERE "
                '(source_aggregate_type=%s AND source_aggregate_identity=%s AND correlation_id LIKE %s '
                "OR %s='deposit' AND idempotency_key=%s AND (processing_status='sent' OR completed_attempts>0) "
                "OR %s='second' AND source_aggregate_type='client_second_payment_settled' AND source_aggregate_identity=%s "
                "AND (processing_status='sent' OR completed_attempts>0) AND EXISTS (SELECT 1 FROM line_notification_source_events s "
                "WHERE CONCAT('line-notification:',s.source_event_identity)=t.correlation_id "
                "AND JSON_UNQUOTE(JSON_EXTRACT(s.facts_snapshot,'$.settlement_identity'))=%s)) "
                "ORDER BY CASE WHEN processing_status='sent' THEN 0 ELSE 1 END,id DESC LIMIT 1"+(' FOR UPDATE' if lock else ''),
                (MANUAL_RECEIPT,payment.payment_stage+':'+payment.settlement_identity,payment.case_no+':%',
                 payment.payment_stage,'deposit-settled:'+payment.settlement_identity,payment.payment_stage,payment.case_no,payment.settlement_identity))
            row=cursor.fetchone()
        return PaymentReceiptHistory(str(row['status']),int(row['attempts'])) if row else None


def _object(value): return json.loads(value) if isinstance(value,str) else value
