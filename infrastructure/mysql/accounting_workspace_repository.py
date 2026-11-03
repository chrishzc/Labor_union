"""Application acknowledgements and historical case markers; no money mutations."""
import json
from dataclasses import asdict
from pymysql.err import IntegrityError

from subsystems.finance_import.accounting_workspace import HistoricalAccountingMarker, HistoricalAccountingAmount, AccountingConflict


class MySqlAccountingWorkspaceState:
    def __init__(self, connection):
        self.connection = connection

    def case_client(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT c.name FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s", (case_no,))
            row = cursor.fetchone()
        if row is None:
            raise LookupError("accounting_case_not_found")
        return str(row["name"])

    def marker(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no,reason,actor,created_at,accounting_snapshot FROM finance_case_accounting_markers WHERE case_no=%s", (case_no,))
            row = cursor.fetchone()
        if row is None:
            return None
        snapshot = row["accounting_snapshot"]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        return HistoricalAccountingMarker(row["case_no"], row["reason"], row["actor"], str(row["created_at"]), tuple(HistoricalAccountingAmount(**item) for item in snapshot["amounts"]))

    def marker_command(self, key):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no,reason,actor,source_versions FROM finance_case_accounting_markers WHERE operation_key=%s", (key,))
            row = cursor.fetchone()
        if row is None:
            return None
        versions = row["source_versions"]
        return row["case_no"], row["reason"], row["actor"], json.loads(versions) if isinstance(versions, str) else versions

    def mark(self, case_no, reason, actor, versions, key, amounts):
        with self.connection.cursor() as cursor:
            try:
                cursor.execute("INSERT INTO finance_case_accounting_markers(case_no,reason,actor,source_versions,operation_key,accounting_snapshot) VALUES (%s,%s,%s,%s,%s,%s)", (case_no, reason, actor, json.dumps(versions, sort_keys=True), key, json.dumps({"amounts": [asdict(item) for item in amounts]}, sort_keys=True)))
            except IntegrityError as error:
                if error.args[0] == 1062:
                    raise AccountingConflict("historical_accounting_already_marked") from None
                raise

    def dismissed(self, case_no, *, for_update=False):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT item_identity,warning_kind,difference_ntd,actor,created_at FROM finance_accounting_dismissals WHERE case_no=%s OR item_identity LIKE 'staff-overpayment:%%'" + (" FOR UPDATE" if for_update else ""), (case_no,))
            rows = cursor.fetchall()
        return {(row["item_identity"], row["warning_kind"], int(row["difference_ntd"])): (row["actor"], str(row["created_at"])) for row in rows}

    def payment_cases(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_no FROM client_ledger_entries UNION "
                "SELECT o.case_no FROM staff_payable_projections p JOIN staff_obligations o "
                "ON o.obligation_identity=p.obligation_identity ORDER BY case_no"
            )
            return tuple(row["case_no"] for row in cursor.fetchall())

    def dismiss(self, case_no, warning, actor):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO finance_accounting_dismissals(case_no,item_identity,warning_kind,difference_ntd,source_version,actor) VALUES (%s,%s,%s,%s,%s,%s)",
                (case_no, warning.item_identity, warning.kind, warning.difference_ntd, warning.source_version, actor),
            )

    def begin(self):
        self.connection.begin()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()
