"""Read Client Finance facts without creating accounts or changing financial state."""
from datetime import date, datetime

from subsystems.client_finance.deposit_payment_query import DepositPayment
from subsystems.client_finance.virtual_account_resolution import resolve_case_virtual_account


class MySqlDepositPaymentQueryRepository:
    def __init__(self, connection):
        self._connection = connection

    def get(self, case_no, *, lock=False):
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s AND status IN ('洽談中','訂單成立','服務中')" + suffix, (case_no,))
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                "SELECT obligation_identity,projection_version,amount_due_ntd,due_date "
                "FROM client_obligations WHERE case_no=%s AND obligation_type='deposit' "
                "AND direction='receivable_from_client' AND status<>'cancelled'" + suffix, (case_no,),
            )
            rows = tuple(cursor.fetchall())
            if len(rows) != 1 or int(rows[0]['amount_due_ntd']) <= 0:
                return None
            obligation = rows[0]
            cursor.execute(
                "SELECT p.settlement_identity,l.occurred_on FROM client_deposit_settlement_projection p "
                "JOIN client_ledger_entries l ON l.id=p.latest_ledger_entry_id AND l.case_no=p.case_no "
                "AND l.entry_type='receipt' WHERE p.case_no=%s AND p.deposit_obligation_identity=%s "
                "AND p.settlement_state='settled' AND p.contracted_amount_ntd=%s "
                "AND p.allocated_net_amount_ntd=p.contracted_amount_ntd" + suffix,
                (case_no, obligation['obligation_identity'], obligation['amount_due_ntd']),
            )
            settlement = cursor.fetchone()
            account = resolve_case_virtual_account(cursor, case_no)
        return DepositPayment(
            case_no, str(obligation['obligation_identity']), int(obligation['projection_version']),
            int(obligation['amount_due_ntd']), _date(obligation['due_date']), account['virtual_account'],
            str(settlement['settlement_identity']) if settlement else None,
            _date(settlement['occurred_on']) if settlement else None,
        )


def _date(value):
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])
