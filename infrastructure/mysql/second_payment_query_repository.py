"""Client Finance-owned read projection; no writes, commits or provider calls."""
from dataclasses import replace
import json

from subsystems.client_finance.second_payment_query import SecondPaymentFinancialFacts


class MySqlSecondPaymentQueryRepository:
    def __init__(self, connection):
        self.connection = connection

    def get(self, case_no, *, lock=False):
        suffix = ' FOR UPDATE' if lock else ''
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT a.aggregate_version,t.second_payment_due_date FROM client_finance_accounts a '
                           'JOIN client_payment_terms t ON t.case_no=a.case_no WHERE a.case_no=%s' + suffix, (case_no,))
            account = cursor.fetchone()
            if not account or account['second_payment_due_date'] is None:
                return None
            cursor.execute('SELECT o.obligation_identity,o.amount_due_ntd,o.current_event_id,o.status,e.after_amount_ntd '
                           'FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id '
                           "WHERE o.case_no=%s AND o.obligation_type='second' AND o.direction='receivable_from_client' "
                           "AND o.status<>'cancelled' ORDER BY o.obligation_identity" + suffix, (case_no,))
            stages = cursor.fetchall()
        if len(stages) != 1 or int(stages[0]['after_amount_ntd']) <= 0:
            return None
        stage = stages[0]
        return SecondPaymentFinancialFacts(case_no, str(stage['obligation_identity']), int(account['aggregate_version']),
            int(stage['current_event_id']), account['second_payment_due_date'], int(stage['after_amount_ntd']),
            int(stage['amount_due_ntd']), stage['status']=='settled')

    def settlement(self, case_no, identity, *, lock=False):
        current = self.get(case_no, lock=lock)
        if not current or not current.settled or current.remaining_amount != 0:
            return None
        suffix = ' FOR UPDATE' if lock else ''
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT payload_snapshot FROM client_finance_outbox WHERE case_no=%s AND intent_type='projection_refresh' "
                           "AND JSON_EXTRACT(payload_snapshot,'$.line_second_payment_notification')=TRUE "
                           "AND JSON_UNQUOTE(JSON_EXTRACT(payload_snapshot,'$.settlement_identity'))=%s" + suffix,
                           (case_no, identity))
            events = cursor.fetchall()
            if len(events) != 1:
                return None
            payload = _object(events[0]['payload_snapshot'])
            if payload['obligation_identities'] != [current.obligation_identity] or int(payload['amount_ntd']) <= 0:
                return None
            cursor.execute('SELECT l.id,l.entry_type,l.reconciliation_reference,l.reversal_of_entry_id,x.amount_ntd '
                           'FROM client_ledger_obligation_allocations x JOIN client_ledger_entries l ON l.id=x.ledger_entry_id '
                           'WHERE x.obligation_identity=%s ORDER BY l.id' + suffix, (current.obligation_identity,))
            ledger = cursor.fetchall()
        net = sum(int(row['amount_ntd']) * (-1 if row['entry_type'] in ('refund','reversal') else 1) for row in ledger)
        receipts = [row for row in ledger if row['entry_type']=='receipt' and row['reconciliation_reference']==identity]
        reversed_ids = {row['reversal_of_entry_id'] for row in ledger if row['reversal_of_entry_id'] is not None}
        received = sum(int(row['amount_ntd']) for row in receipts)
        if (not receipts or any(row['id'] in reversed_ids for row in receipts)
                or net != current.required_amount or received != int(payload['amount_ntd'])):
            return None
        return replace(current, settlement_identity=identity, settled_amount=received)


def _object(value):
    return json.loads(value) if isinstance(value, str) else value
