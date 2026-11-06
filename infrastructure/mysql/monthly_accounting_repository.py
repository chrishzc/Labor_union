"""Report committed owner cash sources; do not expose payloads or accounts."""
import calendar
from datetime import date, datetime
from shared_kernel.clock import TAIPEI_TIME_ZONE
from domains.client_finance.obligation_planning import cancellation_fee_collected

from infrastructure.mysql.case_category_query import CASE_CATEGORY_SQL
from subsystems.finance_import.query import BANK_CASE_PROOFS_SQL
from infrastructure.mysql.finance_import_repository import _integer_bank_amount
from subsystems.finance_import.monthly_accounting import AccountingBankFact
from subsystems.finance_import.monthly_accounting import MonthlyAccountingUnavailable
from subsystems.finance_import.monthly_accounting import AccountingRecognition
from infrastructure.mysql.government_subsidy_manual_period_source import verified_manual_initial_receipt, PERIOD_RECEIPT_PROOF_JSON_SQL


_CASH_FACT_COLUMNS = """b.id,b.transaction_date,b.direction,b.credit,b.debit,b.format_id,p.case_no,
 EXISTS(SELECT 1 FROM client_ledger_entries e WHERE e.finance_import_row_id=b.id AND e.entry_type='receipt') receipt_proof,
 EXISTS(SELECT 1 FROM client_ledger_entries e WHERE e.finance_import_row_id=b.id AND e.entry_type='refund') refund_proof,
 EXISTS(SELECT 1 FROM client_ledger_entries e WHERE e.finance_import_row_id=b.id AND e.entry_type IN ('subsidy_return','subsidy_advance')) subsidy_return_proof,
 EXISTS(SELECT 1 FROM staff_payout_events e WHERE e.finance_import_row_id=b.id) staff_proof,
 (EXISTS(SELECT 1 FROM government_subsidy_transactions t WHERE t.finance_import_row_id=b.id AND t.transaction_status='succeeded')
 OR EXISTS(SELECT 1 FROM government_subsidy_period_entries e WHERE e.finance_import_row_id=b.id)) government_proof
"""
_CASH_FACT_COLUMNS += (',b.currency,b.classification_type,b.reconciliation_status,b.bank_references,b.batch_id,b.source_file,'
    'b.sheet_name,b.source_row,b.source_reference,b.source_bank_account,b.counterparty_account,b.resolved_counterparty_account,'
    '(SELECT ' + PERIOD_RECEIPT_PROOF_JSON_SQL + ' FROM government_subsidy_period_entries entry '
    'WHERE entry.finance_import_row_id=b.id AND entry.reversal_of_id IS NULL LIMIT 1) AS period_receipt')

def _cash_flow(row):
    bank = row.get("format_id") if row.get("format_id") in {"sinopac", "taishin"} else None
    proofs = [name for name in ("receipt", "refund", "subsidy_return", "staff", "government") if row.get(name + "_proof")]
    if len(proofs) != 1:
        return bank, None
    owner = proofs[0]
    incoming = row["direction"] == "incoming"
    if owner == 'government' and incoming and verified_manual_initial_receipt(row, row.get('period_receipt')):
        return None, 'G'
    flow = {("sinopac", True, "receipt"): "C", ("taishin", True, "government"): "G",
            ("sinopac", False, "staff"): "PS", ("taishin", False, "staff"): "PT",
            ("sinopac", False, "refund"): "RS", ("taishin", False, "subsidy_return"): "RT"}
    return bank, flow.get((bank, incoming, owner))


def _cancellation_fee_recognitions(rows, start, end):
    events = []
    last = None
    for row in rows:
        settlement_id = row["settlement_id"]
        cases = (row["case_no"],)
        fee = int(row["fee_ntd"])
        service_due = int(row["service_due_ntd"])
        if settlement_id != last:
            last = settlement_id
            net_cash = int(row["net_received_ntd"])
            collected = cancellation_fee_collected(fee, service_due, net_cash)
            processed_on = date.fromisoformat(row["processed_on"])
            if collected and start <= processed_on <= end:
                events.append(AccountingRecognition(f"cancellation-fee:{settlement_id}", cases,
                    "cancellation_fee_revenue", collected, processed_on.isoformat()))
        if row["entry_id"] is None:
            continue
        processed_on = datetime.fromtimestamp(int(row["entry_epoch"]), TAIPEI_TIME_ZONE).date()
        net_cash += int(row["cash_delta"])
        next_collected = cancellation_fee_collected(fee, service_due, net_cash)
        delta = next_collected - collected
        collected = next_collected
        if delta and start <= processed_on <= end:
            events.append(AccountingRecognition(f"cancellation-fee:{settlement_id}:{row['entry_id']}", cases,
                "cancellation_fee_revenue" if delta > 0 else "cancellation_fee_reversal",
                abs(delta), processed_on.isoformat()))
    return tuple(events)


class MySqlMonthlyAccountingSource:
    def __init__(self, connection):
        self.connection = connection

    def case_categories(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT o.case_no," + CASE_CATEGORY_SQL + " AS category FROM orders o JOIN clients c ON c.id=o.client_id ORDER BY o.case_no")
            return {row["case_no"]: row["category"] for row in cursor.fetchall()}

    def historical_markers(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM finance_case_accounting_markers ORDER BY case_no")
            return tuple(row["case_no"] for row in cursor.fetchall())

    def recognitions(self,start,end):
        from infrastructure.mysql.client_payments_query_repository import CANCELLATION_ALLOCATED_CASH_SQL, CANCELLATION_CASH_JOIN

        end_date=date(end.year,end.month,calendar.monthrange(end.year,end.month)[1])
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT CONCAT('client:',id) identity,case_no,action,amount_ntd,confirmed_on FROM client_finance_noncash_events WHERE confirmed_on BETWEEN %s AND %s "
                "UNION ALL SELECT CONCAT('staff:',n.id),o.case_no,n.action,n.amount_ntd,n.confirmed_on FROM staff_recovery_noncash_events n "
                "JOIN staff_overpayment_recoveries r ON r.recovery_identity=n.recovery_identity JOIN staff_obligations o ON JSON_CONTAINS(r.source_obligation_identities,JSON_QUOTE(o.obligation_identity)) "
                "WHERE n.confirmed_on BETWEEN %s AND %s UNION ALL SELECT CONCAT('government:',op.id),COALESCE(b.case_no,m.case_no),op.action,op.amount_ntd,op.confirmed_on "
                "FROM government_subsidy_period_operations op JOIN government_subsidy_period_balances b ON b.balance_identity=op.balance_identity "
                "JOIN government_subsidy_period_members m ON m.receipt_id=b.root_receipt_id WHERE op.action='loss' AND op.confirmed_on BETWEEN %s AND %s "
                "ORDER BY confirmed_on,identity,case_no",(start,end_date,start,end_date,start,end_date))
            grouped={}
            for row in cursor.fetchall():
                grouped.setdefault(row['identity'],{'row':row,'cases':set()})['cases'].add(row['case_no'])
            cursor.execute(
                "SELECT receipt.id AS settlement_id,receipt.case_no, "
                "JSON_UNQUOTE(JSON_EXTRACT(receipt.result_snapshot,'$.cancellation_settlement.processed_on')) AS processed_on, "
                "JSON_EXTRACT(receipt.result_snapshot,'$.cancellation_settlement.fee_ntd') AS fee_ntd, "
                "JSON_EXTRACT(receipt.result_snapshot,'$.cancellation_settlement.service_due_ntd') AS service_due_ntd, "
                "JSON_EXTRACT(receipt.result_snapshot,'$.cancellation_settlement.net_received_ntd') AS net_received_ntd, "
                "entry.id AS entry_id, UNIX_TIMESTAMP(entry.created_at) AS entry_epoch, SUM(entry.cash_delta) AS cash_delta "
                "FROM client_finance_apply_receipts receipt "
                f"LEFT JOIN ({CANCELLATION_ALLOCATED_CASH_SQL}) entry ON {CANCELLATION_CASH_JOIN} "
                "WHERE JSON_EXTRACT(receipt.result_snapshot,'$.cancellation_settlement.fee_ntd') > 0 "
                "AND JSON_UNQUOTE(JSON_EXTRACT(receipt.result_snapshot,'$.cancellation_settlement.processed_on')) <= %s "
                "GROUP BY receipt.id,entry.id,entry.created_at "
                "ORDER BY receipt.id,entry.id",
                (end_date.isoformat(),),
            )
            fees = _cancellation_fee_recognitions(cursor.fetchall(), start, end_date)
        return (*tuple(AccountingRecognition(identity,tuple(sorted(value['cases'])),value['row']['action'],int(value['row']['amount_ntd']),str(value['row']['confirmed_on'])) for identity,value in grouped.items()), *fees)

    def reporting_cases(self, start: date, end: date):
        end_date = date(end.year, end.month, calendar.monthrange(end.year, end.month)[1])
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_no FROM client_obligations WHERE status<>'cancelled' "
                "AND (due_date BETWEEN %s AND %s OR due_date IS NULL) "
                "UNION SELECT case_no FROM staff_obligations WHERE status<>'cancelled' "
                "AND (due_date BETWEEN %s AND %s OR due_date IS NULL) "
                "UNION SELECT case_no FROM client_over_refund_recoveries WHERE status<>'cancelled' "
                "UNION SELECT o.case_no FROM staff_overpayment_recoveries r JOIN staff_obligations o ON JSON_CONTAINS(r.source_obligation_identities,JSON_QUOTE(o.obligation_identity))", (start, end_date, start, end_date))
            return tuple(row["case_no"] for row in cursor.fetchall())

    def bank_facts(self, start: date, end: date):
        end_date = date(end.year, end.month, calendar.monthrange(end.year, end.month)[1])
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT " + _CASH_FACT_COLUMNS + " FROM finance_import_rows b JOIN (" + BANK_CASE_PROOFS_SQL + ") p ON p.row_id=b.id "
                "WHERE b.transaction_date BETWEEN %s AND %s "
                "ORDER BY b.id,p.case_no", (start, end_date))
            rows = cursor.fetchall()
        return self._facts(rows)

    def case_bank_facts(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT " + _CASH_FACT_COLUMNS + " FROM finance_import_rows b JOIN (" + BANK_CASE_PROOFS_SQL + ") p ON p.row_id=b.id "
                "WHERE b.id IN (SELECT q.row_id FROM (" + BANK_CASE_PROOFS_SQL + ") q WHERE q.case_no=%s) "
                "ORDER BY b.id,p.case_no", (case_no,))
            return self._facts(cursor.fetchall())

    @staticmethod
    def _facts(rows):
        grouped = {}
        for row in rows:
            if row["direction"] not in {"incoming", "outgoing"} or row["transaction_date"] is None:
                raise MonthlyAccountingUnavailable("accounting_bank_source_incomplete")
            grouped.setdefault(row["id"], {"row": row, "cases": set()})["cases"].add(row["case_no"])
        return tuple(AccountingBankFact(f"bank:{identity}", str(entry["row"]["transaction_date"]),
            "in" if entry["row"]["direction"] == "incoming" else "out", _integer_bank_amount(entry["row"]["credit"], entry["row"]["debit"]),
            tuple(sorted(entry["cases"])), *_cash_flow(entry["row"])) for identity, entry in grouped.items())
