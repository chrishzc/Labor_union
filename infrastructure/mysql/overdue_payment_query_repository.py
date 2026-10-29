"""Read stage-local canonical remaining balances, never sum across payment stages."""
from subsystems.client_finance.overdue_payment_query import OverdueClientPayment

_FROM = (
    ' FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id '
    'JOIN orders orders_root ON orders_root.case_no=o.case_no '
    "WHERE o.direction='receivable_from_client' AND o.obligation_type IN ('deposit','first','second') "
    "AND orders_root.status IN ('洽談中','訂單成立','服務中','訂單完成') "
    "AND EXISTS (SELECT 1 FROM order_contract_flow_events flow "
    "WHERE flow.case_no=orders_root.case_no AND flow.event_type='contract_completed' "
    "AND flow.contract_identity=orders_root.contract_identity) "
    "AND o.status='open' AND o.amount_due_ntd>0 AND e.after_amount_ntd>0 AND o.due_date IS NOT NULL"
)
_SELECT = ('SELECT o.case_no,o.obligation_type,o.obligation_identity,o.projection_version,'
           'o.current_event_id,o.due_date,o.amount_due_ntd')


class MySqlOverduePaymentQueryRepository:
    def __init__(self, connection):
        self.connection = connection

    def list(self, day, page, page_size):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) n'+_FROM+' AND o.due_date<%s', (day,))
            total = int(cursor.fetchone()['n'])
            cursor.execute(_SELECT+_FROM+' AND o.due_date<%s ORDER BY o.due_date,o.case_no,o.obligation_type '
                           'LIMIT %s OFFSET %s', (day,page_size,(page-1)*page_size))
            return tuple(_payment(row) for row in cursor.fetchall()), total

    def get(self, identity, *, lock=False):
        with self.connection.cursor() as cursor:
            if lock:
                cursor.execute('SELECT case_no FROM client_obligations WHERE obligation_identity=%s',(identity,))
                owner = cursor.fetchone()
                if owner is None:
                    return None
                # Match the existing order -> Finance -> obligation read-lock order.
                cursor.execute('SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE',(owner['case_no'],))
                cursor.fetchone()
                cursor.execute('SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE',(owner['case_no'],))
                cursor.fetchone()
            cursor.execute(_SELECT+_FROM+' AND o.obligation_identity=%s'+(' FOR UPDATE' if lock else ''), (identity,))
            row = cursor.fetchone()
        return _payment(row) if row else None


def _payment(row):
    return OverdueClientPayment(str(row['case_no']), row['obligation_type'],str(row['obligation_identity']),
        int(row['projection_version']),int(row['current_event_id']),row['due_date'],int(row['amount_due_ntd']))
