"""Finance-owned balances with read-only Orders contract/start-date evidence."""
from infrastructure.mysql.overdue_payment_query_repository import _payment
from subsystems.client_finance.payment_reminder_query import ClientPaymentReminderFacts

_SELECT = (
    'SELECT o.case_no,o.obligation_type,o.obligation_identity,o.projection_version,'
    'o.current_event_id,o.due_date,o.amount_due_ntd,r.actual_start_date,r.status case_status,'
    "EXISTS (SELECT 1 FROM order_contract_flow_events f WHERE f.case_no=r.case_no "
    "AND f.event_type='contract_completed' AND f.contract_identity=r.contract_identity) contract_completed "
)
_FROM = (
    'FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id '
    'JOIN orders r ON r.case_no=o.case_no '
    "WHERE o.direction='receivable_from_client' AND o.obligation_type IN ('deposit','first','second') "
    "AND o.status IN ('open','settled') AND o.due_date IS NOT NULL "
    "AND r.status IN ('洽談中','訂單成立','服務中','訂單完成') "
    "AND (o.obligation_type='first' OR e.after_amount_ntd>0) "
    "AND (o.obligation_type<>'second' OR EXISTS (SELECT 1 FROM client_payment_terms t "
    'WHERE t.case_no=o.case_no AND t.second_payment_due_date=o.due_date)) '
    "AND (o.obligation_type<>'second' OR NOT EXISTS (SELECT 1 FROM client_obligations other "
    "WHERE other.case_no=o.case_no AND other.obligation_type='second' AND other.direction=o.direction "
    "AND other.status<>'cancelled' AND other.obligation_identity<>o.obligation_identity)) "
)


class MySqlClientPaymentReminderQueryRepository:
    def __init__(self, connection):
        self.connection = connection

    def candidates(self, day, after='', limit=100):
        with self.connection.cursor() as cursor:
            cursor.execute(_SELECT+_FROM+
                "AND (o.obligation_type='deposit' OR o.due_date<=%s OR r.actual_start_date=%s) "
                'AND o.obligation_identity>%s ORDER BY o.obligation_identity LIMIT %s', (day,day,after,limit))
            return tuple(_facts(row) for row in cursor.fetchall())

    def get(self, identity, *, lock=False):
        with self.connection.cursor() as cursor:
            if lock:
                cursor.execute('SELECT case_no FROM client_obligations WHERE obligation_identity=%s',(identity,))
                row=cursor.fetchone()
                if row is None:
                    return None
                cursor.execute('SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE',(row['case_no'],))
                cursor.fetchone()
                cursor.execute('SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE',(row['case_no'],))
                cursor.fetchone()
            cursor.execute(_SELECT+_FROM+'AND o.obligation_identity=%s'+(' FOR UPDATE' if lock else ''),(identity,))
            row=cursor.fetchone()
        return _facts(row) if row else None


def _facts(row):
    return ClientPaymentReminderFacts(_payment(row),row['actual_start_date'],bool(row['contract_completed']),str(row['case_status']))
