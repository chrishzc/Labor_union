"""LINE binding and delivery views over committed Finance events; never consumes Orders status."""
from domains.line.identities import LineDeliveryTaskId
from infrastructure.mysql.deposit_payment_query_repository import MySqlDepositPaymentQueryRepository
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from subsystems.line.deposit_notifications import (
    DepositSettlementIntent, DepositNotificationTodo, DepositNotificationTodoPage, REMINDER, SETTLED, payment_source,
)


class MySqlDepositNotificationRepository:
    def __init__(self, connection):
        self._connection = connection

    def contract_completed(self, case_no, *, lock=False):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.case_no FROM orders o WHERE o.case_no=%s "
                "AND EXISTS (SELECT 1 FROM order_contract_flow_events flow "
                "WHERE flow.case_no=o.case_no AND flow.event_type='contract_completed' "
                "AND flow.contract_identity=o.contract_identity)" + (' FOR UPDATE' if lock else ''),
                (case_no,),
            )
            return cursor.fetchone() is not None

    def customer_line_user_id(self, case_no, *, lock=False):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT b.line_user_id FROM orders o JOIN clients c ON c.id=o.client_id "
                "JOIN line_identity_role_bindings b ON b.subject_type='customer' "
                "AND b.subject_reference=CAST(c.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
                "AND b.line_user_id=c.line_user_id "
                "AND b.binding_status='bound' WHERE o.case_no=%s" + (' FOR UPDATE' if lock else ''), (case_no,),
            )
            rows = tuple(cursor.fetchall())
        return str(rows[0]['line_user_id']) if len(rows) == 1 else None

    def existing_delivery(self, key):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM line_delivery_tasks WHERE idempotency_key=%s", (key.value,))
            row = cursor.fetchone()
        return None if row is None else MySqlLineDeliveryTaskRepository(self._connection).get(LineDeliveryTaskId(int(row['id'])))

    def next_settlement(self):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT f.id,f.case_no,p.settlement_identity FROM client_finance_outbox f "
                "JOIN client_deposit_settlement_projection p ON p.case_no=f.case_no AND p.settlement_state='settled' "
                "AND p.settlement_identity=JSON_UNQUOTE(JSON_EXTRACT(f.payload_snapshot,'$.settlement_identity')) "
                "JOIN client_obligations d ON d.obligation_identity=p.deposit_obligation_identity AND d.case_no=p.case_no "
                "AND d.obligation_type='deposit' AND d.direction='receivable_from_client' AND d.status<>'cancelled' "
                "JOIN client_obligation_events e ON e.id=d.current_event_id "
                "AND e.after_amount_ntd=p.contracted_amount_ntd AND e.after_amount_ntd>0 "
                "AND p.allocated_net_amount_ntd=p.contracted_amount_ntd "
                "JOIN client_ledger_entries l ON l.id=p.latest_ledger_entry_id AND l.case_no=p.case_no AND l.entry_type='receipt' "
                "JOIN orders o ON o.case_no=f.case_no AND o.status IN ('洽談中','訂單成立','服務中') "
                "JOIN clients c ON c.id=o.client_id JOIN line_identity_role_bindings b "
                "ON b.subject_type='customer' "
                "AND b.subject_reference=CAST(c.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
                "AND b.line_user_id=c.line_user_id AND b.binding_status='bound' "
                "WHERE f.intent_type='orders_deposit_reconciled' "
                "AND JSON_EXTRACT(f.payload_snapshot,'$.line_deposit_notification')=TRUE "
                "AND NOT EXISTS (SELECT 1 FROM client_obligations other WHERE other.case_no=p.case_no "
                "AND other.obligation_type='deposit' AND other.direction='receivable_from_client' "
                "AND other.status<>'cancelled' AND other.obligation_identity<>d.obligation_identity) "
                "AND NOT EXISTS (SELECT 1 FROM line_delivery_tasks t WHERE "
                "t.idempotency_key=CONCAT('deposit-settled:',p.settlement_identity)) "
                "ORDER BY f.id LIMIT 1 FOR UPDATE SKIP LOCKED", (),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return DepositSettlementIntent(int(row['id']), str(row['case_no']), str(row['settlement_identity']))

    def followups(self, *, page=1, page_size=25, settled=None, case_no=None):
        items = []
        total = 0
        unpaid_total = 0
        settled_total = 0
        page_total = 0
        after_case_no = ''
        page_start = (page - 1) * page_size
        payments = MySqlDepositPaymentQueryRepository(self._connection)
        # Count the same eligible todos as the list, before applying pagination.
        # Read candidates in bounded batches without retaining every payment view.
        while True:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT d.case_no FROM client_obligations d JOIN orders o ON o.case_no=d.case_no "
                    "JOIN client_obligation_events e ON e.id=d.current_event_id "
                    "WHERE d.obligation_type='deposit' AND d.direction='receivable_from_client' "
                    "AND d.status<>'cancelled' AND (d.amount_due_ntd>0 OR (d.status='settled' AND e.after_amount_ntd>0)) AND o.status IN ('洽談中','訂單成立','服務中') "
                    "AND (d.status='settled' OR EXISTS (SELECT 1 FROM order_contract_flow_events flow "
                    "WHERE flow.case_no=o.case_no AND flow.event_type='contract_completed' "
                    "AND flow.contract_identity=o.contract_identity)) "
                    "AND d.case_no>%s" + (" AND d.case_no=%s" if case_no is not None else "")
                    + " ORDER BY d.case_no LIMIT %s",
                    (after_case_no, case_no, 100) if case_no is not None else (after_case_no, 100),
                )
                rows = tuple(cursor.fetchall())
            if not rows:
                break
            for row in rows:
                payment = payments.get(str(row['case_no']))
                if payment is None:
                    continue
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT processing_status FROM line_delivery_tasks WHERE source_aggregate_type=%s "
                        "AND source_aggregate_identity=%s ORDER BY id DESC LIMIT 1",
                        (SETTLED if payment.settled else REMINDER, payment_source(payment)),
                    )
                    delivery = cursor.fetchone()
                # Settled cases without a new notification intent are historical; do not backfill them.
                if payment.settled:
                    with self._connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT id FROM client_finance_outbox WHERE case_no=%s AND intent_type='orders_deposit_reconciled' "
                            "AND JSON_EXTRACT(payload_snapshot,'$.line_deposit_notification')=TRUE "
                            "AND JSON_UNQUOTE(JSON_EXTRACT(payload_snapshot,'$.settlement_identity'))=%s LIMIT 1",
                            (payment.case_no, payment.settlement_identity),
                        )
                        if cursor.fetchone() is None:
                            continue
                if payment.settled and delivery and delivery['processing_status'] == 'sent':
                    continue
                total += 1
                if payment.settled:
                    settled_total += 1
                else:
                    unpaid_total += 1
                if settled is not None and payment.settled != settled:
                    continue
                if page_start <= page_total < page_start + page_size:
                    bound = self.customer_line_user_id(payment.case_no) is not None
                    items.append(DepositNotificationTodo(payment, bound, str(delivery['processing_status']) if delivery else None))
                page_total += 1
            after_case_no = str(rows[-1]['case_no'])
            if len(rows) < 100:
                break
        return DepositNotificationTodoPage(tuple(items), total, unpaid_total, settled_total,
                                          page_total, page_total > page_start + page_size)
