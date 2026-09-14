"""MySQL persistence for audited unpaid-deposit progression overrides."""

import json

from domains.client_finance.deposit_skip import DepositSkipFacts
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.client_finance.deposit_skip_workflow import DepositSkipReceipt, StoredDepositSkipReceipt


class UnitOfWork:
    def __init__(self, connection): self.connection = connection; self.committed = False
    def __enter__(self): self.connection.begin(); return self
    def commit(self): self.connection.commit(); self.committed = True
    def __exit__(self, *_):
        if not self.committed: self.connection.rollback()


class MySqlClientDepositSkipRepository:
    def __init__(self, connection): self.connection = connection
    def load(self, selection, *, for_update):
        with self.connection.cursor() as cursor:
            cursor.execute(_FACTS + (" FOR UPDATE" if for_update else ""), (selection.case_no,)); row = cursor.fetchone()
        if not row: raise ValueError("deposit_skip.finance_facts_not_found")
        return DepositSkipFacts(str(row["case_no"]), int(row["aggregate_version"]), str(row["identity_status"]), int(row["required"]), int(row["received"]), bool(row["override_active"]), str(row["order_status"]))
    def find_receipt(self, key):
        with self.connection.cursor() as cursor: cursor.execute(_RECEIPT, (key.value,)); row = cursor.fetchone()
        if not row: return None
        data = json.loads(row["result_snapshot"]) if isinstance(row["result_snapshot"], str) else row["result_snapshot"]
        return StoredDepositSkipReceipt(PreviewFingerprint(str(row["command_fingerprint"])), DepositSkipReceipt(str(row["case_no"]), int(row["resulting_account_version"]), bool(data["unpaid_progression_allowed"])))
    def apply(self, candidate, request):
        with self.connection.cursor() as cursor:
            if candidate.resulting_account_version > candidate.expected_account_version:
                cursor.execute(_TERMS, (candidate.case_no,)); terms = cursor.fetchone()
                if not terms: raise RuntimeError("deposit_skip.candidate_stale")
                cursor.execute(_EVENT, (candidate.case_no, terms["policy_version"], terms["client_hourly_rate_ntd"], terms["deposit_service_days"], terms["deposit_due_date"], terms["first_payment_due_date"], terms["second_payment_due_date"], candidate.expected_account_version, f"deposit-gate-override:{candidate.fingerprint.value}", request.idempotency_key.value, request.actor.actor_id, request.reason)); event_id = int(cursor.lastrowid)
                cursor.execute("UPDATE client_payment_terms SET current_event_id=%s WHERE case_no=%s AND current_event_id=%s", (event_id, candidate.case_no, terms["current_event_id"]))
                if cursor.rowcount != 1: raise RuntimeError("deposit_skip.candidate_stale")
                cursor.execute("UPDATE client_finance_accounts SET aggregate_version=%s WHERE case_no=%s AND aggregate_version=%s", (candidate.resulting_account_version, candidate.case_no, candidate.expected_account_version))
                if cursor.rowcount != 1: raise RuntimeError("deposit_skip.candidate_stale")
            cursor.execute("INSERT INTO client_finance_outbox (case_no,intent_type,intent_key,payload_snapshot) VALUES (%s,'projection_refresh',%s,%s)", (candidate.case_no, f"deposit-gate-override:{candidate.fingerprint.value}", _json({"case_no": candidate.case_no, "account_version": candidate.resulting_account_version, "unpaid_progression_allowed": True, "actor": request.actor.actor_id, "reason": request.reason})))
    def save_receipt(self, key, stored, preview):
        receipt = stored.receipt
        with self.connection.cursor() as cursor: cursor.execute(_SAVE, (key.value, stored.command_fingerprint.value, preview.value, receipt.case_no, receipt.account_version, _json({"unpaid_progression_allowed": receipt.unpaid_progression_allowed})))


def _json(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
_FACTS = ("SELECT a.case_no,a.aggregate_version,c.identity_status,o2.status order_status,COALESCE((SELECT e2.after_amount_ntd FROM client_obligations o JOIN client_obligation_events e2 ON e2.id=o.current_event_id WHERE o.case_no=a.case_no AND o.obligation_type='deposit' LIMIT 1),0) required,COALESCE((SELECT SUM(CASE l.entry_type WHEN 'receipt' THEN x.amount_ntd WHEN 'adjustment' THEN x.amount_ntd WHEN 'refund' THEN -x.amount_ntd WHEN 'reversal' THEN -x.amount_ntd END) FROM client_obligations o JOIN client_ledger_obligation_allocations x ON x.obligation_identity=o.obligation_identity JOIN client_ledger_entries l ON l.id=x.ledger_entry_id WHERE o.case_no=a.case_no AND o.obligation_type='deposit'),0) received,(e.source_event_identity LIKE 'deposit-gate-override:%%') override_active FROM client_finance_accounts a JOIN client_payment_terms t ON t.case_no=a.case_no JOIN client_payment_terms_events e ON e.id=t.current_event_id JOIN clients c ON c.case_no=a.case_no JOIN orders o2 ON o2.case_no=a.case_no WHERE a.case_no=%s")
_TERMS = "SELECT policy_version,client_hourly_rate_ntd,deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,current_event_id FROM client_payment_terms WHERE case_no=%s FOR UPDATE"
_EVENT = "INSERT INTO client_payment_terms_events (case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,expected_account_version,source_event_identity,idempotency_key,actor,reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
_RECEIPT = "SELECT command_fingerprint,case_no,resulting_account_version,result_snapshot FROM client_finance_apply_receipts WHERE idempotency_key=%s FOR UPDATE"
_SAVE = "INSERT INTO client_finance_apply_receipts (idempotency_key,command_fingerprint,preview_fingerprint,case_no,resulting_account_version,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s)"
