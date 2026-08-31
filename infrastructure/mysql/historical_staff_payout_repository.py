"""MySQL adapter for Staff Payables historical payout evidence."""

from __future__ import annotations

from contextlib import contextmanager
import json

from domains.staff_payables.historical_payout import (
    HistoricalStaffObligation,
    HistoricalStaffPayoutFacts,
    HistoricalStaffPayoutProjection,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.staff_payables.historical_payment_settlement import (
    HistoricalStaffPayoutReceipt,
    StoredHistoricalStaffPayoutReceipt,
)


class HistoricalStaffPayoutMySqlUnitOfWork(MySqlUnitOfWork):
    """Names the Staff Payables outer transaction; the repository never commits."""


class MySqlHistoricalStaffPayoutRepository:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._request = None

    def load(self, case_no: str, staff_id: int, *, for_update: bool) -> HistoricalStaffPayoutFacts:
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            if for_update:
                cursor.execute(
                    "INSERT IGNORE INTO staff_payable_accounts "
                    "(staff_id,aggregate_version) VALUES (%s,0)",
                    (staff_id,),
                )
            cursor.execute(
                "SELECT aggregate_version FROM staff_payable_accounts "
                f"WHERE staff_id=%s{suffix}",
                (staff_id,),
            )
            account = cursor.fetchone()
            cursor.execute(
                "SELECT id FROM historical_order_adoption_receipts "
                "WHERE case_no=%s AND outcome='adopted' "
                f"ORDER BY id DESC LIMIT 1{suffix}",
                (case_no,),
            )
            adoption = cursor.fetchone()
            cursor.execute(
                "SELECT obligation_identity,case_no,staff_id,amount_due_ntd,payroll_version,"
                "direction,status FROM staff_obligations WHERE case_no=%s AND staff_id=%s "
                f"ORDER BY obligation_identity{suffix}",
                (case_no, staff_id),
            )
            obligation_rows = tuple(cursor.fetchall())
            cursor.execute(_STAFF_BANK_CANDIDATES_SQL + suffix, (staff_id,))
            bank_rows = tuple(cursor.fetchall())
        return HistoricalStaffPayoutFacts(
            case_no,
            staff_id,
            0 if account is None else int(account["aggregate_version"]),
            None if adoption is None else int(adoption["id"]),
            adoption is not None,
            tuple(str(row["id"]) for row in bank_rows),
            tuple(_obligation(row) for row in obligation_rows),
        )

    def load_projections(
        self, case_no: str, staff_id: int
    ) -> tuple[HistoricalStaffPayoutProjection, ...]:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT obligation_identity,amount_snapshot_ntd,"
                "obligation_payroll_version FROM historical_staff_payout_projections "
                "WHERE case_no=%s AND staff_id=%s ORDER BY obligation_identity",
                (case_no, staff_id),
            )
            rows = tuple(cursor.fetchall())
        return tuple(
            HistoricalStaffPayoutProjection(
                str(row["obligation_identity"]),
                int(row["amount_snapshot_ntd"]),
                int(row["obligation_payroll_version"]),
            )
            for row in rows
        )

    def find_receipt(self, key):
        with _cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        if row is None:
            return None
        snapshot = _json_object(row["result_snapshot"])
        if snapshot.get("receipt_kind") != "historical_staff_payout":
            return StoredHistoricalStaffPayoutReceipt(
                PreviewFingerprint(str(row["command_fingerprint"])),
                _foreign_receipt(key.value),
            )
        return StoredHistoricalStaffPayoutReceipt(
            PreviewFingerprint(str(row["command_fingerprint"])),
            HistoricalStaffPayoutReceipt(
                str(snapshot["event_identity"]),
                str(snapshot["case_no"]),
                int(snapshot["staff_id"]),
                tuple(str(value) for value in snapshot["obligation_identities"]),
                int(snapshot["amount_snapshot_ntd"]),
                int(snapshot["resulting_staff_payables_version"]),
                PreviewFingerprint(str(snapshot["preview_fingerprint"])),
            ),
        )

    def append_event(self, request, candidate, event_identity):
        self._request = request
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _EVENT_INSERT_SQL,
                (
                    event_identity,
                    request.intent.case_no,
                    request.intent.staff_id,
                    request.intent.confirmation_kind.value,
                    request.intent.payment_date,
                    request.intent.payment_date_unknown_reason,
                    request.intent.source_availability.value,
                    request.intent.evidence_reference,
                    candidate.adoption_receipt_id,
                    candidate.staff_payables_version,
                    candidate.staff_payables_version + 1,
                    request.idempotency_key.value,
                    request.actor.actor_id,
                    request.reason,
                    request.correlation_id.value,
                ),
            )
            event_id = int(cursor.lastrowid or 0)
        if event_id <= 0:
            raise RuntimeError("historical_staff_payout_event_missing")
        return event_id

    def append_obligation_links(self, event_id, candidate):
        rows = [
            (
                event_id,
                item.identity,
                item.amount_due_ntd,
                item.payroll_version,
                ordinal,
            )
            for ordinal, item in enumerate(candidate.obligations, start=1)
        ]
        with _cursor(self._connection) as cursor:
            cursor.executemany(_LINK_INSERT_SQL, rows)

    def upsert_projections(self, event_id, candidate, resulting_version):
        request = self._require_request()
        rows = [
            (
                item.identity,
                item.case_no,
                item.staff_id,
                event_id,
                request.intent.confirmation_kind.value,
                item.amount_due_ntd,
                item.payroll_version,
                resulting_version,
            )
            for item in candidate.obligations
        ]
        with _cursor(self._connection) as cursor:
            cursor.executemany(_PROJECTION_UPSERT_SQL, rows)
            cursor.execute(
                "UPDATE staff_payable_accounts SET aggregate_version=%s "
                "WHERE staff_id=%s AND aggregate_version=%s",
                (resulting_version, request.intent.staff_id, candidate.staff_payables_version),
            )
            if int(cursor.rowcount) != 1:
                raise RuntimeError("historical_staff_payout_candidate_stale")

    def append_source_outbox(self, event_id, candidate, event_identity):
        request = self._require_request()
        payload = {
            "source_kind": "historical_staff_payout",
            "event_identity": event_identity,
            "case_no": request.intent.case_no,
            "staff_id": request.intent.staff_id,
            "confirmation_kind": request.intent.confirmation_kind.value,
            "obligation_identities": request.intent.obligation_identities,
            "resulting_staff_payables_version": candidate.staff_payables_version + 1,
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                (
                    event_id,
                    f"historical-staff-payout-source:{event_identity}",
                    _json(payload),
                ),
            )

    def save_receipt(self, key, stored):
        receipt = stored.receipt
        snapshot = {
            "receipt_kind": "historical_staff_payout",
            "event_identity": receipt.event_identity,
            "case_no": receipt.case_no,
            "staff_id": receipt.staff_id,
            "obligation_identities": receipt.obligation_identities,
            "amount_snapshot_ntd": receipt.amount_snapshot_ntd,
            "resulting_staff_payables_version": receipt.resulting_staff_payables_version,
            "preview_fingerprint": receipt.preview_fingerprint.value,
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (
                    key.value,
                    stored.command_fingerprint.value,
                    receipt.preview_fingerprint.value,
                    receipt.staff_id,
                    _json(snapshot),
                ),
            )

    def _require_request(self):
        if self._request is None:
            raise RuntimeError("historical_staff_payout_apply_request_missing")
        return self._request


def _obligation(row):
    return HistoricalStaffObligation(
        str(row["obligation_identity"]),
        str(row["case_no"]),
        int(row["staff_id"]),
        int(row["amount_due_ntd"]),
        int(row["payroll_version"]),
        str(row["direction"]),
        str(row["status"]),
    )


def _foreign_receipt(key: str) -> HistoricalStaffPayoutReceipt:
    placeholder = PreviewFingerprint("0" * 64)
    return HistoricalStaffPayoutReceipt(
        f"foreign-staff-payables-receipt:{key}", "unknown", 1, ("unknown",), 0, 0, placeholder
    )


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("historical_staff_payout_receipt_invalid")
    return parsed


@contextmanager
def _cursor(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


_STAFF_BANK_CANDIDATES_SQL = (
    "SELECT fir.id FROM finance_import_rows fir "
    "JOIN finance_import_classification_events classification ON classification.id=("
    "SELECT MAX(latest.id) FROM finance_import_classification_events latest "
    "WHERE latest.finance_import_row_id=fir.id) "
    "LEFT JOIN staff_payout_events payout ON payout.finance_import_row_id=fir.id "
    "WHERE COALESCE(classification.classification_type,fir.classification_type) "
    "IN ('staff_payout','staff_salary','staff_legacy_subsidy') "
    "AND JSON_CONTAINS(classification.target_identities,"
    "JSON_QUOTE(CONCAT('staff:',CAST(%s AS CHAR)))) "
    "AND fir.reconciliation_status='pending' AND fir.direction='outgoing' "
    "AND fir.transaction_date IS NOT NULL AND payout.id IS NULL ORDER BY fir.id"
)
_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,result_snapshot FROM staff_payables_apply_receipts "
    "WHERE idempotency_key=%s FOR UPDATE"
)
_EVENT_INSERT_SQL = (
    "INSERT INTO historical_staff_payout_events "
    "(event_identity,case_no,staff_id,confirmation_kind,payer_role,payee_role,"
    "payment_date,payment_date_unknown_reason,source_availability,evidence_reference,"
    "historical_adoption_receipt_id,expected_staff_payables_version,"
    "resulting_staff_payables_version,idempotency_key,actor_id,reason,correlation_id) "
    "VALUES (%s,%s,%s,%s,'union','staff',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_LINK_INSERT_SQL = (
    "INSERT INTO historical_staff_payout_obligation_links "
    "(event_id,obligation_identity,amount_snapshot_ntd,obligation_payroll_version,link_ordinal) "
    "VALUES (%s,%s,%s,%s,%s)"
)
_PROJECTION_UPSERT_SQL = (
    "INSERT INTO historical_staff_payout_projections "
    "(obligation_identity,case_no,staff_id,current_event_id,confirmation_kind,"
    "amount_snapshot_ntd,obligation_payroll_version,staff_payables_version) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
    "case_no=VALUES(case_no),staff_id=VALUES(staff_id),current_event_id=VALUES(current_event_id),"
    "confirmation_kind=VALUES(confirmation_kind),amount_snapshot_ntd=VALUES(amount_snapshot_ntd),"
    "obligation_payroll_version=VALUES(obligation_payroll_version),"
    "staff_payables_version=VALUES(staff_payables_version)"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO historical_staff_payout_source_outbox "
    "(event_id,intent_key,payload_snapshot) VALUES (%s,%s,%s)"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO staff_payables_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,staff_id,result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s)"
)


__all__ = ["HistoricalStaffPayoutMySqlUnitOfWork", "MySqlHistoricalStaffPayoutRepository"]
