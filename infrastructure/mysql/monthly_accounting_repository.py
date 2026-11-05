"""Report only committed bank sources; do not expose statement payloads or accounts."""
import calendar
from datetime import date

from infrastructure.mysql.case_category_query import CASE_CATEGORY_SQL
from infrastructure.mysql.finance_statement_archive_repository import _PROOFS
from infrastructure.mysql.finance_import_repository import _integer_bank_amount
from subsystems.finance_import.monthly_accounting import AccountingBankFact
from subsystems.finance_import.monthly_accounting import MonthlyAccountingUnavailable
from subsystems.finance_import.monthly_accounting import AccountingRecognition


_CASH_FACT_COLUMNS = """b.id,b.transaction_date,b.direction,b.credit,b.debit,b.format_id,p.case_no,
 EXISTS(SELECT 1 FROM client_ledger_entries e WHERE e.finance_import_row_id=b.id AND e.entry_type='receipt') receipt_proof,
 EXISTS(SELECT 1 FROM client_ledger_entries e WHERE e.finance_import_row_id=b.id AND e.entry_type='refund') refund_proof,
 EXISTS(SELECT 1 FROM client_ledger_entries e WHERE e.finance_import_row_id=b.id AND e.entry_type IN ('subsidy_return','subsidy_advance')) subsidy_return_proof,
 EXISTS(SELECT 1 FROM staff_payout_events e WHERE e.finance_import_row_id=b.id) staff_proof,
 (EXISTS(SELECT 1 FROM government_subsidy_transactions t WHERE t.finance_import_row_id=b.id AND t.transaction_status='succeeded')
 OR EXISTS(SELECT 1 FROM government_subsidy_period_entries e WHERE e.finance_import_row_id=b.id)) government_proof
"""

def _cash_flow(row):
    bank = row.get("format_id") if row.get("format_id") in {"sinopac", "taishin"} else None
    proofs = [name for name in ("receipt", "refund", "subsidy_return", "staff", "government") if row.get(name + "_proof")]
    if len(proofs) != 1:
        return bank, None
    owner = proofs[0]
    incoming = row["direction"] == "incoming"
    flow = {("sinopac", True, "receipt"): "C", ("taishin", True, "government"): "G",
            ("sinopac", False, "staff"): "PS", ("taishin", False, "staff"): "PT",
            ("sinopac", False, "refund"): "RS", ("taishin", False, "subsidy_return"): "RT"}
    return bank, flow.get((bank, incoming, owner))


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
        return tuple(AccountingRecognition(identity,tuple(sorted(value['cases'])),value['row']['action'],int(value['row']['amount_ntd']),str(value['row']['confirmed_on'])) for identity,value in grouped.items())

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
                "SELECT " + _CASH_FACT_COLUMNS + " FROM finance_import_rows b JOIN (" + _PROOFS + ") p ON p.row_id=b.id "
                "WHERE b.transaction_date BETWEEN %s AND %s "
                "ORDER BY b.id,p.case_no", (start, end_date))
            rows = cursor.fetchall()
        return self._facts(rows)

    def case_bank_facts(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT " + _CASH_FACT_COLUMNS + " FROM finance_import_rows b JOIN (" + _PROOFS + ") p ON p.row_id=b.id "
                "WHERE b.id IN (SELECT q.row_id FROM (" + _PROOFS + ") q WHERE q.case_no=%s) "
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
