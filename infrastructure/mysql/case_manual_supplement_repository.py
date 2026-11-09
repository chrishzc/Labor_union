"""Persist manual provenance; borrow the caller's transaction for official owner Apply."""
from dataclasses import asdict
import hashlib
import json

from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType, ClientRefundPurpose
from domains.staff_payables.reconciliation import StaffPayoutDifferenceMode, StaffPayoutEventType
from subsystems.client_finance.reconciliation_workflow import (
    ReconciliationSelection, ClientReconciliationApplyRequest, ClientReconciliationWorkflow,
)
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalSelection, ClientRefundReversalApplyRequest, ClientRefundReversalWorkflow,
)
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutSelection, StaffPayoutApplyRequest, StaffPayoutReconciliationWorkflow,
)
from subsystems.client_finance.virtual_account_resolution import resolve_case_virtual_account
from subsystems.finance_import.case_manual_supplement import ManualSupplementConflict, ManualSupplementResult
from infrastructure.mysql.client_receipt_reconciliation_repository import MySqlClientReceiptReconciliationRepository
from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository
from infrastructure.mysql.staff_payout_repository import MySqlStaffPayoutRepository
from infrastructure.mysql.finance_import_owning_domain_composite import BorrowedTransactionUnitOfWork


class MySqlCaseManualSupplementRepository:
    def __init__(self, connection):
        self.connection = connection

    def lock_case(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE", (case_no,))
            if cursor.fetchone() is None:
                raise LookupError("manual_case_not_found")

    def reserve_or_replay(self, key, digest):
        with self.connection.cursor() as cursor:
            # Acquire the unique key before reading it: no read-then-insert gap-lock race.
            cursor.execute("INSERT INTO finance_statement_commands "
                           "(idempotency_key,command_digest,result_identity,saved_count,excluded_count,actor) "
                           "VALUES (%s,%s,NULL,0,0,'manual-reservation') "
                           "ON DUPLICATE KEY UPDATE idempotency_key=idempotency_key", (key, digest))
            cursor.execute("SELECT command_digest,result_identity FROM finance_statement_commands "
                           "WHERE idempotency_key=%s FOR UPDATE", (key,))
            stored = cursor.fetchone()
            if stored["command_digest"] != digest:
                raise ManualSupplementConflict("manual_supplement_idempotency_conflict")
            if stored["result_identity"] is None:
                return None
            if not str(stored["result_identity"]).startswith("manual:"):
                raise ManualSupplementConflict("manual_supplement_idempotency_conflict")
            row_id = int(stored["result_identity"].split(":", 1)[1])
            cursor.execute("SELECT bank_references FROM finance_import_rows WHERE id=%s", (row_id,))
            row = cursor.fetchone()
            if row is None:
                raise ManualSupplementConflict("manual_supplement_receipt_unavailable")
            command = json.loads(row["bank_references"])["manual_supplement"]["command"]
            return self._result(cursor, command, row_id)

    def reconcile(self, command, key, digest):
        with self.connection.cursor() as cursor:
            target = self._target(cursor, command)
            row_id = self._source(cursor, command, key, digest, target)
            # Trusted linkage is visible only within this transaction; failure rolls it back.
            cursor.execute("UPDATE finance_statement_commands SET result_identity=%s,saved_count=1,actor=%s "
                           "WHERE idempotency_key=%s AND command_digest=%s AND result_identity IS NULL",
                           (f"manual:{row_id}", command.actor, key, digest))
            if cursor.rowcount != 1:
                raise ManualSupplementConflict("manual_supplement_idempotency_conflict")
        if command.direction == "government_subsidy":
            self._government(command, key, row_id)
        else:
            self._post(command, row_id, target, digest)
        with self.connection.cursor() as cursor:
            return self._result(cursor, asdict(command), row_id)

    def _target(self, cursor, command):
        if command.direction == "government_subsidy":
            return {}
        if command.direction == "staff_salary":
            cursor.execute("SELECT o.obligation_identity,o.case_no,o.staff_id,s.name FROM staff_obligations o "
                           "JOIN staff s ON s.id=o.staff_id WHERE o.obligation_identity=%s "
                           "AND o.case_no=%s AND o.direction='payable_to_staff' AND o.status='open' FOR UPDATE",
                           (command.target_item, command.case_no))
        else:
            direction = "receivable_from_client" if command.direction == "client_receipt" else "payable_to_client"
            cursor.execute("SELECT obligation_identity,case_no,obligation_type FROM client_obligations "
                           "WHERE obligation_identity=%s AND case_no=%s AND direction=%s "
                           "AND status='open' AND amount_due_ntd>0 FOR UPDATE",
                           (command.target_item, command.case_no, direction))
        target = cursor.fetchone()
        if target is None:
            raise ValueError("manual_target_not_open_in_case")
        return target

    def _source(self, cursor, command, key, digest, target):
        classification = {"client_receipt": "client_receipt", "staff_salary": "staff_payout",
                          "client_refund": "client_refund", "government_subsidy": "government_subsidy"}[command.direction]
        if command.direction == "client_refund" and target["obligation_type"] in {"subsidy_return", "subsidy_advance"}:
            classification = "client_subsidy_return"
        resolved = resolve_case_virtual_account(cursor, command.case_no)
        account = resolved.get("virtual_account") if resolved.get("result") == "resolved" else None
        memo = command.reason or "人工補登"
        if command.bank == "taishin" and command.direction == "staff_salary":
            memo = target["name"]
        elif command.bank == "taishin" and classification == "client_subsidy_return" and account:
            memo = account[-6:]
        proof = {"key": key, "digest": digest, "actor": command.actor,
                 "case_no": command.case_no, "direction": command.direction,
                 "obligations": [command.target_item], "command": asdict(command)}
        references = {"source": "manual_supplement", "bank": command.bank,
                      "manual_supplement": proof}
        # Raw bank fields absent from a manual source remain absent; never fabricate accounts.
        raw = {"source": "manual_supplement", "transaction_date": command.transaction_date,
               "amount_ntd": command.amount_ntd, "direction": command.direction, "reason": command.reason}
        cursor.execute("INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count,status) "
                       "VALUES (%s,'manual_supplement',1,1,'completed')", (command.bank,))
        batch_id = cursor.lastrowid
        incoming = command.direction in {"client_receipt", "government_subsidy"}
        cursor.execute("INSERT INTO finance_import_rows "
                       "(dedup_fingerprint,batch_id,format_id,transaction_date,direction,credit,debit,currency,"
                       "summary,memo,cancellation_code,bank_references,warnings,classification_type,"
                       "reconciliation_status,raw_payload,matched_identity_ids) "
                       "VALUES (%s,%s,%s,%s,%s,%s,%s,'TWD','人工補登',%s,%s,%s,'[]',%s,'pending',%s,%s)",
                       (hashlib.sha256(f"manual:{key}".encode()).hexdigest(), batch_id, command.bank,
                        command.transaction_date, "incoming" if incoming else "outgoing",
                        command.amount_ntd if incoming else None, None if incoming else command.amount_ntd,
                        memo, account if command.direction == "client_receipt" else None,
                        json.dumps(references, ensure_ascii=False), classification,
                        json.dumps(raw, ensure_ascii=False), json.dumps([command.target_item])))
        row_id = cursor.lastrowid
        cursor.execute("INSERT INTO finance_import_classification_events "
                       "(batch_id,finance_import_row_id,classification_version,canonical_fact_version,"
                       "classification_type,disposition,decision_facts_fingerprint,target_identities,evidence,"
                       "available_actions,actor,reason) VALUES (%s,%s,1,1,%s,'manual_review',%s,%s,'[]','[]',%s,'人工補登')",
                       (batch_id, row_id, classification, digest, json.dumps([command.target_item]), command.actor))
        return row_id

    def _post(self, c, row_id, target, digest):
        banks, obligations = (str(row_id),), (c.target_item,)
        correlation, actor, key = CorrelationId(f"manual:{row_id}"), ActorContext(c.actor), IdempotencyKey(f"manual-owner:{row_id}:{digest}")
        reason = c.reason or "人工補登"
        if c.direction == "client_receipt":
            repository = MySqlClientReceiptReconciliationRepository(self.connection)
            workflow = ClientReconciliationWorkflow(repository, BorrowedTransactionUnitOfWork)
            selection = ReconciliationSelection(c.case_no, None, banks, obligations,
                                                allow_overage_disposition=c.settlement_mode == "overage",
                                                allow_partial_receipt=c.settlement_mode == "partial")
            preview = workflow.preview(selection)
            request = ClientReconciliationApplyRequest(selection, ExpectedVersion(preview.account_version),
                        preview.fingerprint, key, actor, reason, correlation)
        elif c.direction == "staff_salary":
            repository = MySqlStaffPayoutRepository(self.connection)
            workflow = StaffPayoutReconciliationWorkflow(repository, BorrowedTransactionUnitOfWork)
            mode = {"partial": StaffPayoutDifferenceMode.UNDERPAYMENT,
                    "overage": StaffPayoutDifferenceMode.OVERPAYMENT}.get(c.settlement_mode)
            selection = StaffPayoutSelection(StaffPayoutEventType.PAYOUT, banks, obligations, difference_mode=mode)
            preview = workflow.preview(selection, correlation)
            request = StaffPayoutApplyRequest(selection, ExpectedVersion(preview.staff_payables_version),
                        ExpectedVersion(preview.bank_facts_version), preview.fingerprint, key, actor, reason, correlation)
        else:
            repository = MySqlClientRefundReversalRepository(self.connection)
            workflow = ClientRefundReversalWorkflow(repository, BorrowedTransactionUnitOfWork)
            purpose = ClientRefundPurpose.SUBSIDY_RETURN if target["obligation_type"] in {"subsidy_return", "subsidy_advance"} else ClientRefundPurpose.CUSTOMER_REFUND
            selection = ClientRefundReversalSelection(c.case_no,
                        ClientFinanceCorrectionType.REFUND_OVERAGE if c.settlement_mode == "overage" else ClientFinanceCorrectionType.REFUND,
                        purpose, banks, obligations, allow_partial_refund_recovery=c.settlement_mode == "partial")
            preview = workflow.preview(selection, correlation)
            request = ClientRefundReversalApplyRequest(selection, ExpectedVersion(preview.account_version),
                        preview.fingerprint, key, actor, reason, correlation)
        repository.bind_apply_request(request)
        try:
            workflow.apply(request)
        finally:
            repository.clear_apply_request()

    def _result(self, cursor, command, row_id):
        table = {"staff_salary": "staff_payout_events", "government_subsidy": "government_subsidy_period_entries"}.get(command["direction"], "client_ledger_entries")
        cursor.execute(f"SELECT id FROM {table} WHERE finance_import_row_id=%s ORDER BY id LIMIT 1", (row_id,))
        entry = cursor.fetchone()
        if entry is None:
            raise ManualSupplementConflict("manual_supplement_receipt_unavailable")
        return ManualSupplementResult(command["case_no"], row_id, int(entry["id"]), command["direction"],
                                      command["target_item"], command["amount_ntd"], True)

    def _government(self, c, key, row_id):
        # Existing government supplement posting is outside this correction's business scope.
        with self.connection.cursor() as cursor:
            self._post_government(cursor, c.case_no, c.transaction_date, c.amount_ntd, key, c.actor, row_id)
            cursor.execute("UPDATE finance_import_rows SET reconciliation_status='reconciled' WHERE id=%s", (row_id,))

    @staticmethod
    def _post_government(cursor, case_no, transaction_date, amount_ntd, idempotency_key, actor, row_id):
        # 政府入款核銷（台新入款 G）
        cursor.execute(
            "SELECT COALESCE(actual_end_date, end_date) as service_end FROM orders WHERE case_no=%s",
            (case_no,),
        )
        ord_row = cursor.fetchone()
        svc_date = ord_row["service_end"] if ord_row and ord_row["service_end"] else transaction_date
        year_val = int(str(svc_date)[:4])
        month_val = int(str(svc_date)[5:7]) if len(str(svc_date)) >= 7 else 1
        quarter_val = (month_val - 1) // 3 + 1
        cursor.execute(
            """
            INSERT INTO government_subsidy_period_entries (
                period_unit, period_year, period_index, period_start, period_end,
                finance_import_row_id, amount_ntd, paid_on, idempotency_key, actor
            ) VALUES (
                'quarter', %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                year_val,
                quarter_val,
                f"{year_val}-{(quarter_val-1)*3+1:02d}-01",
                f"{year_val}-{quarter_val*3:02d}-28",
                row_id,
                amount_ntd,
                transaction_date,
                idempotency_key,
                actor,
            ),
        )
        entry_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO government_subsidy_period_members (
                receipt_id, case_no, service_end_date, amount_ntd
            ) VALUES (%s, %s, %s, %s)
            """,
            (entry_id, case_no, svc_date, amount_ntd),
        )
