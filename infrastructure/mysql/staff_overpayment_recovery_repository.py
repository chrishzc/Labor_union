"""MySQL port for canonical-bank collection of staff overpayment recoveries."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator

from domains.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecovery, StaffOverpaymentRecoveryStatus, StaffRecoveryIncomingBankFact,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecoveryAction, StaffOverpaymentRecoveryApplyRequest,
    StaffOverpaymentRecoveryFacts, StaffOverpaymentRecoveryPreview,
    StaffOverpaymentRecoveryReceipt, StaffOverpaymentRecoverySelection,
    StoredStaffOverpaymentRecoveryReceipt,
)
from subsystems.staff_payables.overpayment_recovery_matching import (
    StaffOverpaymentRecoveryMatchingFacts,
    StaffOverpaymentRecoveryMatchingReceipt,
    StoredStaffOverpaymentRecoveryMatchingReceipt,
)


class MySqlStaffOverpaymentRecoveryRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, selection: StaffOverpaymentRecoverySelection, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT recovery_identity,staff_id,remaining_amount_ntd,status,aggregate_version "
                "FROM staff_overpayment_recoveries WHERE recovery_identity=%s" + suffix,
                (selection.recovery_identity,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError("staff_overpayment_recovery_not_open")
            recovery = StaffOverpaymentRecovery(str(row["recovery_identity"]), int(row["staff_id"]), MoneyNTD(int(row["remaining_amount_ntd"])), StaffOverpaymentRecoveryStatus(str(row["status"])), int(row["aggregate_version"]))
            account_version = _account_version(cursor, recovery.staff_id, suffix)
            bank_fact = self._load_bank_fact(cursor, selection, recovery.staff_id, suffix)
        return StaffOverpaymentRecoveryFacts(
            recovery,
            account_version,
            bank_fact,
            selection.action is StaffOverpaymentRecoveryAction.ADJUST,
        )

    def find_receipt(self, key: IdempotencyKey):
        with _cursor(self._connection) as cursor:
            cursor.execute("SELECT command_fingerprint,result_snapshot FROM staff_overpayment_recovery_apply_receipts WHERE idempotency_key=%s FOR UPDATE", (key.value,))
            row = cursor.fetchone()
        if row is None:
            return None
        payload = _object(row["result_snapshot"])
        receipt = StaffOverpaymentRecoveryReceipt(
            str(payload["recovery_identity"]), int(payload["recovery_version"]),
            int(payload["staff_payables_version"]), int(payload["remaining_after_ntd"]),
            str(payload["resulting_status"]), PreviewFingerprint(str(payload["preview_fingerprint"])),
        )
        return StoredStaffOverpaymentRecoveryReceipt(PreviewFingerprint(str(row["command_fingerprint"])), receipt)

    def load_matching(self, selection, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT recovery_identity,staff_id,aggregate_version FROM staff_overpayment_recoveries "
                "WHERE recovery_identity=%s AND status IN ('open','partially_recovered')" + suffix,
                (selection.recovery_identity,),
            )
            recovery = cursor.fetchone()
            if recovery is None:
                raise ValueError("staff_overpayment_recovery_not_open")
            staff_id = int(recovery["staff_id"])
            version = _account_version(cursor, staff_id, suffix)
            fact = self._load_bank_fact_for_matching(cursor, selection.finance_import_row_identity, staff_id, suffix)
        return StaffOverpaymentRecoveryMatchingFacts(
            staff_id, int(recovery["aggregate_version"]), version, fact,
        )

    def _load_bank_fact_for_matching(self, cursor, identity, staff_id, suffix):
        row_id = int(identity)
        cursor.execute(
            "SELECT id,credit,transaction_date,direction,currency,classification_type,reconciliation_status,resolved_counterparty_account "
            "FROM finance_import_rows WHERE id=%s" + suffix, (row_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return False
        eligible = (row["direction"] == "incoming" and row["currency"] == "TWD"
                    and row["classification_type"] in ("staff_payout_return", "staff_salary_return")
                    and row["reconciliation_status"] == "pending" and row["credit"] is not None)
        if not eligible:
            return False
        cursor.execute("SELECT COUNT(*) AS count FROM staff_bank_accounts WHERE staff_id=%s AND account_no=%s AND is_primary=1", (staff_id, row["resolved_counterparty_account"]))
        return int(cursor.fetchone()["count"]) == 1

    def find_matching_receipt(self, key: IdempotencyKey):
        with _cursor(self._connection) as cursor:
            cursor.execute("SELECT command_fingerprint,result_snapshot FROM staff_overpayment_recovery_matching_receipts WHERE idempotency_key=%s FOR UPDATE", (key.value,))
            row = cursor.fetchone()
        if row is None:
            return None
        payload = _object(row["result_snapshot"])
        receipt = StaffOverpaymentRecoveryMatchingReceipt(
            str(payload["matching_identity"]), int(payload["matching_version"]),
            str(payload["recovery_identity"]), int(payload["staff_id"]),
            str(payload["finance_import_row_identity"]), int(payload["recovery_version"]),
            int(payload["staff_payables_version"]), PreviewFingerprint(str(payload["preview_fingerprint"])),
        )
        return StoredStaffOverpaymentRecoveryMatchingReceipt(PreviewFingerprint(str(row["command_fingerprint"])), receipt)

    def persist_matching(self, request, preview, receipt, command_fingerprint):
        candidate = preview.candidate
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO staff_overpayment_recovery_matchings (matching_identity,recovery_identity,staff_id,finance_import_row_id,recovery_version,staff_payables_version,matching_version,actor,reason,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (receipt.matching_identity, receipt.recovery_identity, receipt.staff_id,
                 int(receipt.finance_import_row_identity), receipt.recovery_version,
                 receipt.staff_payables_version, receipt.matching_version,
                 request.actor.actor_id, request.reason, request.idempotency_key.value),
            )
            snapshot = _matching_receipt_payload(receipt)
            cursor.execute("INSERT INTO staff_overpayment_recovery_matching_receipts (idempotency_key,command_fingerprint,preview_fingerprint,matching_identity,result_snapshot) VALUES (%s,%s,%s,%s,%s)", (request.idempotency_key.value, command_fingerprint.value, request.preview_fingerprint.value, receipt.matching_identity, json.dumps(snapshot, sort_keys=True)))
            cursor.execute("INSERT INTO staff_payables_outbox (staff_id,intent_key,intent_type,payload_snapshot) VALUES (%s,%s,'staff_overpayment_recovery_matched',%s)", (candidate.staff_id, f"staff-overpayment-recovery-match:{request.idempotency_key.value}", json.dumps(snapshot, sort_keys=True)))

    def persist(self, request: StaffOverpaymentRecoveryApplyRequest, preview: StaffOverpaymentRecoveryPreview, receipt: StaffOverpaymentRecoveryReceipt, command_fingerprint: PreviewFingerprint) -> None:
        candidate = preview.candidate
        bank_row_id = None if request.selection.action is StaffOverpaymentRecoveryAction.ADJUST else int(request.selection.finance_import_row_identity or 0)
        event_type = "authorized_adjustment" if bank_row_id is None else "cash_recovered"
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "UPDATE staff_overpayment_recoveries SET remaining_amount_ntd=%s,status=%s,aggregate_version=%s "
                "WHERE recovery_identity=%s AND aggregate_version=%s",
                (receipt.remaining_after_ntd, receipt.resulting_status, receipt.recovery_version, receipt.recovery_identity, preview.recovery_version),
            )
            if cursor.rowcount != 1:
                raise ValueError("staff_overpayment_recovery_stale")
            cursor.execute(
                "INSERT INTO staff_overpayment_recovery_events (recovery_identity,event_type,finance_import_row_id,before_remaining_ntd,after_remaining_ntd,resulting_status,idempotency_key,actor,reason,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (receipt.recovery_identity, event_type, bank_row_id, candidate.remaining_before.amount, receipt.remaining_after_ntd, receipt.resulting_status, request.idempotency_key.value, request.actor.actor_id, request.reason, request.correlation_id.value),
            )
            cursor.execute("UPDATE staff_payable_accounts SET aggregate_version=%s WHERE staff_id=%s AND aggregate_version=%s", (receipt.staff_payables_version, candidate.staff_id, preview.staff_payables_version))
            if cursor.rowcount != 1:
                raise ValueError("staff_overpayment_recovery_stale")
            cursor.execute("INSERT INTO staff_payables_outbox (staff_id,intent_key,intent_type,payload_snapshot) VALUES (%s,%s,'staff_overpayment_recovery_updated',%s)", (candidate.staff_id, f"staff-overpayment-recovery:{request.idempotency_key.value}", json.dumps({"recovery_identity": receipt.recovery_identity, "status": receipt.resulting_status, "matching_identity": request.selection.matching_identity}, sort_keys=True)))
            if request.selection.matching_identity is not None and receipt.resulting_status == "recovered":
                cursor.execute("INSERT INTO staff_payables_outbox (staff_id,intent_key,intent_type,payload_snapshot) VALUES (%s,%s,'staff_overpayment_recovery_collected',%s)", (candidate.staff_id, f"staff-overpayment-recovery-collected:{request.idempotency_key.value}", json.dumps({"recovery_identity": receipt.recovery_identity, "status": receipt.resulting_status, "matching_identity": request.selection.matching_identity}, sort_keys=True)))
            cursor.execute("INSERT INTO staff_overpayment_recovery_apply_receipts (idempotency_key,command_fingerprint,preview_fingerprint,recovery_identity,result_snapshot) VALUES (%s,%s,%s,%s,%s)", (request.idempotency_key.value, command_fingerprint.value, receipt.preview_fingerprint.value, receipt.recovery_identity, json.dumps(_receipt_payload(receipt), sort_keys=True)))

    def _load_bank_fact(self, cursor, selection, staff_id, suffix):
        if selection.action is StaffOverpaymentRecoveryAction.ADJUST:
            return None
        row_id = int(selection.finance_import_row_identity or 0)
        if selection.matching_identity is not None:
            cursor.execute("SELECT 1 FROM staff_overpayment_recovery_matchings WHERE matching_identity=%s AND recovery_identity=%s AND staff_id=%s AND finance_import_row_id=%s AND matching_version=%s" + suffix, (selection.matching_identity, selection.recovery_identity, staff_id, row_id, selection.matching_version))
            if cursor.fetchone() is None:
                raise ValueError("staff_overpayment_recovery_matching_stale")
        cursor.execute("SELECT id,credit,transaction_date,direction,currency,classification_type,reconciliation_status,resolved_counterparty_account FROM finance_import_rows WHERE id=%s" + suffix, (row_id,))
        row = cursor.fetchone()
        if row is None or row["direction"] != "incoming" or row["currency"] != "TWD" or row["classification_type"] not in ("staff_payout_return", "staff_salary_return") or row["reconciliation_status"] != "pending" or row["credit"] is None:
            raise ValueError("bank_fact_not_eligible")
        cursor.execute("SELECT COUNT(*) AS count FROM staff_bank_accounts WHERE staff_id=%s AND account_no=%s AND is_primary=1", (staff_id, row["resolved_counterparty_account"]))
        if int(cursor.fetchone()["count"]) != 1:
            raise ValueError("staff_overpayment_recovery_target_ambiguous")
        return StaffRecoveryIncomingBankFact(str(row["id"]), staff_id, MoneyNTD(int(row["credit"])), str(row["transaction_date"]), True)


def _account_version(cursor, staff_id, suffix):
    cursor.execute("SELECT aggregate_version FROM staff_payable_accounts WHERE staff_id=%s" + suffix, (staff_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError("staff_overpayment_recovery_not_open")
    return int(row["aggregate_version"])


def _receipt_payload(receipt):
    return {"recovery_identity": receipt.recovery_identity, "recovery_version": receipt.recovery_version, "staff_payables_version": receipt.staff_payables_version, "remaining_after_ntd": receipt.remaining_after_ntd, "resulting_status": receipt.resulting_status, "preview_fingerprint": receipt.preview_fingerprint.value}


def _matching_receipt_payload(receipt):
    return {"matching_identity": receipt.matching_identity, "matching_version": receipt.matching_version, "recovery_identity": receipt.recovery_identity, "staff_id": receipt.staff_id, "finance_import_row_identity": receipt.finance_import_row_identity, "recovery_version": receipt.recovery_version, "staff_payables_version": receipt.staff_payables_version, "preview_fingerprint": receipt.preview_fingerprint.value}


def _object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("staff_overpayment_recovery_receipt_invalid")
    return parsed


@contextmanager
def _cursor(connection) -> Iterator[object]:
    with connection.cursor() as cursor:
        yield cursor
