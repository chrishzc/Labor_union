"""File: client_over_refund_recovery_repository.py
Description: 客戶退款超額追償的 MySQL collection、adjustment 與 outbox 持久化。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from typing import Iterator

from pymysql.err import IntegrityError, OperationalError

from domains.client_finance.over_refund_recovery import (
    ClientOverRefundRecovery,
    ClientOverRefundRecoveryStatus,
    ClientRecoveryIncomingBankFact,
)
from infrastructure.mysql.client_refund_reversal_repository import ClientRefundReversalMySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.over_refund_recovery_workflow import (
    ClientOverRefundRecoveryAction,
    ClientOverRefundRecoveryFacts,
    ClientOverRefundRecoveryReceipt,
    StoredClientOverRefundRecoveryReceipt,
)
from subsystems.client_finance.over_refund_recovery_matching_workflow import (
    ClientOverRefundRecoveryMatchingFacts,
    ClientOverRefundRecoveryMatchingReceipt,
    StoredClientOverRefundRecoveryMatchingReceipt,
)
from subsystems.client_finance.client_over_refund_recovery_query import (
    ClientOverRefundRecoveryMatchingQueryFact,
    ClientOverRefundRecoveryQueryFacts,
    ClientOverRefundRecoveryQuerySelection,
)


class MySqlClientOverRefundRecoveryRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, selection, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s" + suffix,
                (selection.case_no,),
            )
            account = cursor.fetchone()
            if account is None:
                raise ValueError("client_over_refund_recovery_owner_unavailable")
            cursor.execute(
                "SELECT recovery_identity,case_no,amount_due_ntd,status,projection_version "
                "FROM client_over_refund_recoveries WHERE recovery_identity=%s AND case_no=%s" + suffix,
                (selection.recovery_identity, selection.case_no),
            )
            recovery = cursor.fetchone()
            bank = self._load_bank_fact(cursor, selection, suffix)
        if recovery is None:
            raise ValueError("client_over_refund_recovery_not_found")
        if selection.action is ClientOverRefundRecoveryAction.COLLECT and bank is None:
            raise ValueError("finance_import_row_not_found")
        return ClientOverRefundRecoveryFacts(
            ClientOverRefundRecovery(
                str(recovery["recovery_identity"]), str(recovery["case_no"]),
                MoneyNTD(int(recovery["amount_due_ntd"])),
                ClientOverRefundRecoveryStatus(str(recovery["status"])),
                int(recovery["projection_version"]),
            ),
            ClientRecoveryIncomingBankFact(
                str(bank["id"]), selection.case_no, MoneyNTD(_positive(bank.get("credit"))),
                _date_text(bank.get("transaction_date")), _eligible(bank),
            ),
            0 if account is None else int(account["aggregate_version"]),
            selection.action is ClientOverRefundRecoveryAction.ADJUST,
        )

    def query_recovery(self, selection: ClientOverRefundRecoveryQuerySelection):
        """Read the committed owner root and every immutable matching without locking or writes."""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT recovery_identity,case_no,finance_import_row_id,amount_due_ntd,status,projection_version "
                "FROM client_over_refund_recoveries WHERE recovery_identity=%s",
                (selection.recovery_identity,),
            )
            recovery = cursor.fetchone()
            if recovery is None:
                return None
            if str(recovery["case_no"]) != selection.case_no:
                raise ValueError("client_over_refund_recovery_owner_mismatch")
            cursor.execute(
                "SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s",
                (selection.case_no,),
            )
            account = cursor.fetchone()
            cursor.execute(
                "SELECT matching_identity,matching_version,finance_import_row_id "
                "FROM client_over_refund_recovery_matchings "
                "WHERE recovery_identity=%s AND case_no=%s ORDER BY matching_identity",
                (selection.recovery_identity, selection.case_no),
            )
            matchings = tuple(
                ClientOverRefundRecoveryMatchingQueryFact(
                    str(row["matching_identity"]),
                    int(row["matching_version"]),
                    _row_reference(row["finance_import_row_id"]),
                )
                for row in cursor.fetchall()
            )
        return ClientOverRefundRecoveryQueryFacts(
            case_no=str(recovery["case_no"]),
            recovery_identity=str(recovery["recovery_identity"]),
            remaining_amount_ntd=int(recovery["amount_due_ntd"]),
            status=str(recovery["status"]),
            recovery_version=int(recovery["projection_version"]),
            account_version=int(account["aggregate_version"]),
            source_row_reference=_row_reference(recovery["finance_import_row_id"]),
            current_matchings=matchings,
        )

    def _load_bank_fact(self, cursor, selection, suffix):
        if selection.action is ClientOverRefundRecoveryAction.ADJUST:
            return None
        self._require_matching(cursor, selection, suffix)
        cursor.execute(
            "SELECT fir.id,fir.transaction_date,fir.credit,fir.debit,fir.direction,fir.currency,"
            "COALESCE(event.classification_type,fir.classification_type) classification_type,"
            "fir.reconciliation_status,ledger.id ledger_id "
            "FROM finance_import_rows fir "
            "LEFT JOIN finance_import_classification_events event ON event.id=("
            "SELECT MAX(latest.id) FROM finance_import_classification_events latest "
            "WHERE latest.finance_import_row_id=fir.id) "
            "LEFT JOIN client_ledger_entries ledger ON ledger.finance_import_row_id=fir.id "
            "WHERE fir.id=%s" + suffix,
            (_row_id(selection.finance_import_row_identity),),
        )
        return cursor.fetchone()

    def _require_matching(self, cursor, selection, suffix):
        if selection.matching_identity is None:
            return
        cursor.execute(
            "SELECT 1 FROM client_over_refund_recovery_matchings "
            "WHERE matching_identity=%s AND recovery_identity=%s AND finance_import_row_id=%s "
            "AND matching_version=%s" + suffix,
            (selection.matching_identity, selection.recovery_identity,
             _row_id(selection.finance_import_row_identity), selection.matching_version),
        )
        if cursor.fetchone() is None:
            raise ValueError("client_over_refund_recovery_matching_stale")

    def find_receipt(self, key):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM client_over_refund_recovery_apply_receipts "
                "WHERE idempotency_key=%s FOR UPDATE", (key.value,),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    "SELECT command_fingerprint,result_snapshot FROM client_over_refund_recovery_adjustment_receipts "
                    "WHERE idempotency_key=%s FOR UPDATE", (key.value,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        payload = json.loads(row["result_snapshot"])
        receipt = ClientOverRefundRecoveryReceipt(
            payload["recovery_identity"], int(payload["account_version"]),
            int(payload["recovery_version"]), int(payload["remaining_after_ntd"]),
            payload["resulting_status"], PreviewFingerprint(payload["preview_fingerprint"]),
            payload.get("evidence_reference"),
        )
        return StoredClientOverRefundRecoveryReceipt(PreviewFingerprint(row["command_fingerprint"]), receipt)

    def load_matching(self, selection, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s" + suffix,
                (selection.case_no,),
            )
            account = cursor.fetchone()
            cursor.execute(
                "SELECT projection_version FROM client_over_refund_recoveries "
                "WHERE recovery_identity=%s AND case_no=%s AND status IN ('open','partially_recovered')" + suffix,
                (selection.recovery_identity, selection.case_no),
            )
            recovery = cursor.fetchone()
            bank = self._load_matching_bank_fact(cursor, selection, suffix)
        if recovery is None:
            raise ValueError("client_over_refund_recovery_not_found")
        if bank is None:
            raise ValueError("finance_import_row_not_found")
        return ClientOverRefundRecoveryMatchingFacts(
            int(recovery["projection_version"]),
            0 if account is None else int(account["aggregate_version"]),
            _eligible(bank),
        )

    def _load_matching_bank_fact(self, cursor, selection, suffix):
        cursor.execute(
            "SELECT fir.id,fir.transaction_date,fir.credit,fir.debit,fir.direction,fir.currency,"
            "COALESCE(event.classification_type,fir.classification_type) classification_type,"
            "fir.reconciliation_status,ledger.id ledger_id "
            "FROM finance_import_rows fir "
            "LEFT JOIN finance_import_classification_events event ON event.id=("
            "SELECT MAX(latest.id) FROM finance_import_classification_events latest "
            "WHERE latest.finance_import_row_id=fir.id) "
            "LEFT JOIN client_ledger_entries ledger ON ledger.finance_import_row_id=fir.id "
            "WHERE fir.id=%s" + suffix,
            (_row_id(selection.finance_import_row_identity),),
        )
        return cursor.fetchone()

    def find_matching_receipt(self, key):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM client_over_refund_recovery_matching_receipts "
                "WHERE idempotency_key=%s FOR UPDATE", (key.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = json.loads(row["result_snapshot"])
        receipt = ClientOverRefundRecoveryMatchingReceipt(
            payload["matching_identity"], int(payload["matching_version"]),
            payload["recovery_identity"], payload["finance_import_row_identity"],
            int(payload["recovery_version"]), int(payload["account_version"]),
            PreviewFingerprint(payload["preview_fingerprint"]), payload.get("evidence_reference"),
        )
        return StoredClientOverRefundRecoveryMatchingReceipt(
            PreviewFingerprint(row["command_fingerprint"]), receipt)

    def persist_matching(self, request, preview, receipt, command_fingerprint):
        candidate = preview.candidate
        with _cursor(self._connection) as cursor:
            row_id = _row_id(candidate.finance_import_row_identity)
            cursor.execute(
                "INSERT INTO client_over_refund_recovery_matchings "
                "(matching_identity,case_no,recovery_identity,finance_import_row_id,recovery_version,account_version,"
                "matching_version,actor,reason,evidence_reference,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (receipt.matching_identity, candidate.case_no, candidate.recovery_identity, row_id,
                 candidate.recovery_version, candidate.account_version, receipt.matching_version,
                 request.actor.actor_id, request.reason, request.evidence_reference or "", request.idempotency_key.value),
            )
            snapshot = _matching_receipt_payload(receipt)
            cursor.execute(
                "INSERT INTO client_over_refund_recovery_matching_receipts "
                "(idempotency_key,command_fingerprint,preview_fingerprint,matching_identity,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s)",
                (request.idempotency_key.value, command_fingerprint.value,
                 request.preview_fingerprint.value, receipt.matching_identity, _json(snapshot)),
            )

    # One method owns all writes so a collection cannot commit as a partial accounting result.
    def persist(self, request, preview, receipt, command_fingerprint) -> None:
        if request.selection.action is ClientOverRefundRecoveryAction.ADJUST:
            self._persist_adjustment(request, preview, receipt, command_fingerprint)
            return
        self._persist_collection(request, preview, receipt, command_fingerprint)

    def _persist_collection(self, request, preview, receipt, command_fingerprint) -> None:
        candidate = preview.candidate
        with _cursor(self._connection) as cursor:
            row_id = _row_id(candidate.bank_fact_identity)
            cursor.execute(
                "INSERT INTO client_ledger_entries (case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
                "reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) "
                "VALUES (%s,%s,'receipt',%s,%s,%s,NULL,%s,%s,%s)",
                (candidate.case_no, row_id, candidate.fingerprint.value, candidate.amount_received.amount,
                 _date_from_text(preview.candidate.bank_fact_identity, self._connection),
                 f"{request.idempotency_key.value}:ledger", request.actor.actor_id, request.reason),
            )
            ledger_id = int(cursor.lastrowid)
            cursor.execute(
                "UPDATE finance_import_rows SET reconciliation_status='reconciled',"
                "reconciliation_reference=%s,reconciled_at=CURRENT_TIMESTAMP "
                "WHERE id=%s AND reconciliation_status='pending'",
                (f"client-over-refund-recovery:{candidate.recovery_identity}", row_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("bank_fact_not_eligible")
            cursor.execute(
                "UPDATE client_over_refund_recoveries SET amount_due_ntd=%s,status=%s,projection_version=%s "
                "WHERE recovery_identity=%s AND case_no=%s AND projection_version=%s AND amount_due_ntd=%s",
                (candidate.remaining_after.amount, candidate.resulting_status.value, receipt.recovery_version,
                 candidate.recovery_identity, candidate.case_no, preview.recovery_version,
                 candidate.remaining_before.amount),
            )
            if cursor.rowcount != 1:
                raise ValueError("client_finance_candidate_stale")
            cursor.execute(
                "INSERT INTO client_over_refund_recovery_events "
                "(recovery_identity,event_type,finance_import_row_id,receipt_ledger_entry_id,before_amount_ntd,after_amount_ntd,"
                "idempotency_key,actor,reason,evidence_reference) VALUES (%s,'collected',%s,%s,%s,%s,%s,%s,%s,%s)",
                (candidate.recovery_identity, row_id, ledger_id, candidate.remaining_before.amount,
                 candidate.remaining_after.amount, f"{request.idempotency_key.value}:event",
                 request.actor.actor_id, request.reason, request.evidence_reference or ""),
            )
            cursor.execute(
                "INSERT INTO client_finance_accounts (case_no,aggregate_version) VALUES (%s,%s) "
                "ON DUPLICATE KEY UPDATE aggregate_version=IF(aggregate_version=%s,VALUES(aggregate_version),aggregate_version)",
                (candidate.case_no, receipt.account_version, preview.account_version),
            )
            if cursor.rowcount not in (1, 2):
                raise ValueError("client_finance_candidate_stale")
            snapshot = _receipt_payload(receipt)
            cursor.execute(
                "INSERT INTO client_over_refund_recovery_apply_receipts "
                "(idempotency_key,command_fingerprint,preview_fingerprint,recovery_identity,finance_import_row_id,receipt_ledger_entry_id,"
                "resulting_version,remaining_after_ntd,resulting_status,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (request.idempotency_key.value, command_fingerprint.value, request.preview_fingerprint.value,
                 candidate.recovery_identity, row_id, ledger_id, receipt.recovery_version,
                 candidate.remaining_after.amount, candidate.resulting_status.value, _json(snapshot)),
            )

    def _persist_adjustment(self, request, preview, receipt, command_fingerprint) -> None:
        candidate = preview.candidate
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "UPDATE client_over_refund_recoveries SET amount_due_ntd=%s,status=%s,projection_version=%s "
                "WHERE recovery_identity=%s AND case_no=%s AND projection_version=%s AND amount_due_ntd=%s",
                (candidate.remaining_after.amount, candidate.resulting_status.value,
                 receipt.recovery_version, candidate.recovery_identity, candidate.case_no,
                 preview.recovery_version, candidate.remaining_before.amount),
            )
            if cursor.rowcount != 1:
                raise ValueError("client_finance_candidate_stale")
            cursor.execute(
                "INSERT INTO client_over_refund_recovery_events "
                "(recovery_identity,event_type,finance_import_row_id,receipt_ledger_entry_id,before_amount_ntd,after_amount_ntd,"
                "idempotency_key,actor,reason,evidence_reference) VALUES (%s,'authorized_adjustment',NULL,NULL,%s,%s,%s,%s,%s,%s)",
                (candidate.recovery_identity, candidate.remaining_before.amount,
                 candidate.remaining_after.amount, f"{request.idempotency_key.value}:event",
                 request.actor.actor_id, request.reason, request.evidence_reference or ""),
            )
            cursor.execute(
                "INSERT INTO client_finance_accounts (case_no,aggregate_version) VALUES (%s,%s) "
                "ON DUPLICATE KEY UPDATE aggregate_version=IF(aggregate_version=%s,VALUES(aggregate_version),aggregate_version)",
                (candidate.case_no, receipt.account_version, preview.account_version),
            )
            if cursor.rowcount not in (1, 2):
                raise ValueError("client_finance_candidate_stale")
            cursor.execute(
                "INSERT INTO client_over_refund_recovery_adjustment_receipts "
                "(idempotency_key,command_fingerprint,preview_fingerprint,recovery_identity,resulting_version,remaining_after_ntd,resulting_status,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (request.idempotency_key.value, command_fingerprint.value,
                 request.preview_fingerprint.value, candidate.recovery_identity,
                 receipt.recovery_version, candidate.remaining_after.amount,
                 candidate.resulting_status.value, _json(_receipt_payload(receipt))),
            )


def _eligible(bank) -> bool:
    return (bank.get("direction") == "incoming" and _positive(bank.get("credit")) > 0
            and not bank.get("debit") and bank.get("currency") == "TWD"
            and bank.get("classification_type") == "client_receipt"
            and bank.get("reconciliation_status") == "pending" and bank.get("ledger_id") is None
            and isinstance(bank.get("transaction_date"), date))


def _date_from_text(identity, connection):
    with _cursor(connection) as cursor:
        cursor.execute("SELECT transaction_date FROM finance_import_rows WHERE id=%s", (_row_id(identity),))
        return cursor.fetchone()["transaction_date"]


def _positive(value):
    return int(value or 0) if int(value or 0) > 0 else 0


def _row_id(value):
    row_id = int(value)
    if row_id <= 0:
        raise ValueError("finance_import_row_not_found")
    return row_id


def _row_reference(value):
    row_id = _row_id(value)
    return f"finance-import-row:{row_id}"


def _date_text(value):
    return value.isoformat() if isinstance(value, date) else "0001-01-01"


def _receipt_payload(receipt):
    return {"recovery_identity": receipt.recovery_identity, "account_version": receipt.account_version,
            "recovery_version": receipt.recovery_version, "remaining_after_ntd": receipt.remaining_after_ntd,
            "resulting_status": receipt.resulting_status, "preview_fingerprint": receipt.preview_fingerprint.value,
            "evidence_reference": receipt.evidence_reference}


def _matching_receipt_payload(receipt):
    return {
        "matching_identity": receipt.matching_identity,
        "matching_version": receipt.matching_version,
        "recovery_identity": receipt.recovery_identity,
        "finance_import_row_identity": receipt.finance_import_row_identity,
        "recovery_version": receipt.recovery_version,
        "account_version": receipt.account_version,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "evidence_reference": receipt.evidence_reference,
    }


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))




@contextmanager
def _cursor(connection) -> Iterator[object]:
    with connection.cursor() as cursor:
        yield cursor


__all__ = ["ClientRefundReversalMySqlUnitOfWork", "MySqlClientOverRefundRecoveryRepository"]
