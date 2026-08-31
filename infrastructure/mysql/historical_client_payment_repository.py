"""MySQL adapter for Client Finance historical payment evidence."""

from __future__ import annotations

from contextlib import contextmanager
import json

from domains.client_finance.historical_payment import (
    HistoricalClientDirection,
    HistoricalClientObligation,
    HistoricalClientPaymentFacts,
    HistoricalClientPaymentProjection,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.client_finance.historical_payment_settlement import (
    HistoricalClientPaymentReceipt,
    StoredHistoricalClientPaymentReceipt,
)


class HistoricalClientPaymentMySqlUnitOfWork(MySqlUnitOfWork):
    """Names the Client Finance outer transaction; the repository never commits."""


class MySqlHistoricalClientPaymentRepository:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._request = None

    def load(self, case_no: str, *, for_update: bool) -> HistoricalClientPaymentFacts:
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            if for_update:
                cursor.execute(
                    "INSERT IGNORE INTO client_finance_accounts "
                    "(case_no,aggregate_version) VALUES (%s,0)",
                    (case_no,),
                )
            cursor.execute(
                "SELECT aggregate_version FROM client_finance_accounts "
                f"WHERE case_no=%s{suffix}",
                (case_no,),
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
                "SELECT obligation_identity,case_no,obligation_type,direction,"
                "amount_due_ntd,projection_version,status FROM client_obligations "
                f"WHERE case_no=%s ORDER BY obligation_identity{suffix}",
                (case_no,),
            )
            obligation_rows = tuple(cursor.fetchall())
            cursor.execute(_CLIENT_BANK_CANDIDATES_SQL + suffix, (case_no,))
            bank_rows = tuple(cursor.fetchall())
        return HistoricalClientPaymentFacts(
            case_no,
            0 if account is None else int(account["aggregate_version"]),
            None if adoption is None else int(adoption["id"]),
            adoption is not None,
            tuple(str(row["id"]) for row in bank_rows),
            tuple(_obligation(row) for row in obligation_rows),
        )

    def load_projections(self, case_no: str) -> tuple[HistoricalClientPaymentProjection, ...]:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT obligation_identity,amount_snapshot_ntd,"
                "obligation_projection_version FROM historical_client_payment_projections "
                "WHERE case_no=%s ORDER BY obligation_identity",
                (case_no,),
            )
            rows = tuple(cursor.fetchall())
        return tuple(
            HistoricalClientPaymentProjection(
                str(row["obligation_identity"]),
                int(row["amount_snapshot_ntd"]),
                int(row["obligation_projection_version"]),
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
        if snapshot.get("receipt_kind") != "historical_client_payment":
            return StoredHistoricalClientPaymentReceipt(
                PreviewFingerprint(str(row["command_fingerprint"])),
                _foreign_receipt(key.value),
            )
        return StoredHistoricalClientPaymentReceipt(
            PreviewFingerprint(str(row["command_fingerprint"])),
            HistoricalClientPaymentReceipt(
                str(snapshot["event_identity"]),
                str(snapshot["case_no"]),
                tuple(str(value) for value in snapshot["obligation_identities"]),
                int(snapshot["amount_snapshot_ntd"]),
                int(snapshot["resulting_account_version"]),
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
                    request.intent.direction.value,
                    request.intent.confirmation_kind.value,
                    "client" if request.intent.direction is HistoricalClientDirection.RECEIVABLE_FROM_CLIENT else "union",
                    "union" if request.intent.direction is HistoricalClientDirection.RECEIVABLE_FROM_CLIENT else "client",
                    request.intent.payment_date,
                    request.intent.payment_date_unknown_reason,
                    request.intent.source_availability.value,
                    request.intent.evidence_reference,
                    candidate.adoption_receipt_id,
                    candidate.account_version,
                    candidate.account_version + 1,
                    request.idempotency_key.value,
                    request.actor.actor_id,
                    request.reason,
                    request.correlation_id.value,
                ),
            )
            event_id = int(cursor.lastrowid or 0)
        if event_id <= 0:
            raise RuntimeError("historical_client_payment_event_missing")
        return event_id

    def append_obligation_links(self, event_id, candidate):
        rows = [
            (
                event_id,
                item.identity,
                item.amount_due_ntd,
                item.obligation_type,
                item.direction.value,
                item.projection_version,
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
                event_id,
                request.intent.confirmation_kind.value,
                item.amount_due_ntd,
                item.projection_version,
                resulting_version,
            )
            for item in candidate.obligations
        ]
        with _cursor(self._connection) as cursor:
            cursor.executemany(_PROJECTION_UPSERT_SQL, rows)
            cursor.execute(
                "UPDATE client_finance_accounts SET aggregate_version=%s "
                "WHERE case_no=%s AND aggregate_version=%s",
                (resulting_version, request.intent.case_no, candidate.account_version),
            )
            if int(cursor.rowcount) != 1:
                raise RuntimeError("historical_client_payment_candidate_stale")

    def append_source_outbox(self, event_id, candidate, event_identity):
        request = self._require_request()
        payload = {
            "source_kind": "historical_client_payment",
            "event_identity": event_identity,
            "case_no": request.intent.case_no,
            "direction": request.intent.direction.value,
            "confirmation_kind": request.intent.confirmation_kind.value,
            "obligation_identities": request.intent.obligation_identities,
            "resulting_account_version": candidate.account_version + 1,
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                (
                    event_id,
                    f"historical-client-payment-source:{event_identity}",
                    _json(payload),
                ),
            )

    def save_receipt(self, key, stored):
        receipt = stored.receipt
        snapshot = {
            "receipt_kind": "historical_client_payment",
            "event_identity": receipt.event_identity,
            "case_no": receipt.case_no,
            "obligation_identities": receipt.obligation_identities,
            "amount_snapshot_ntd": receipt.amount_snapshot_ntd,
            "resulting_account_version": receipt.resulting_account_version,
            "preview_fingerprint": receipt.preview_fingerprint.value,
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (
                    key.value,
                    stored.command_fingerprint.value,
                    receipt.preview_fingerprint.value,
                    receipt.case_no,
                    receipt.resulting_account_version,
                    _json(snapshot),
                ),
            )

    def _require_request(self):
        if self._request is None:
            raise RuntimeError("historical_client_payment_apply_request_missing")
        return self._request


def _obligation(row):
    return HistoricalClientObligation(
        str(row["obligation_identity"]),
        str(row["case_no"]),
        str(row["obligation_type"]),
        HistoricalClientDirection(str(row["direction"])),
        int(row["amount_due_ntd"]),
        int(row["projection_version"]),
        str(row["status"]),
    )


def _foreign_receipt(key: str) -> HistoricalClientPaymentReceipt:
    placeholder = PreviewFingerprint("0" * 64)
    return HistoricalClientPaymentReceipt(
        f"foreign-client-finance-receipt:{key}", "unknown", ("unknown",), 0, 0, placeholder
    )


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("historical_client_payment_receipt_invalid")
    return parsed


@contextmanager
def _cursor(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


_CLIENT_BANK_CANDIDATES_SQL = (
    "SELECT fir.id FROM finance_import_rows fir "
    "JOIN orders selected_order ON selected_order.case_no=%s "
    "JOIN finance_import_classification_events classification ON classification.id=("
    "SELECT MAX(latest.id) FROM finance_import_classification_events latest "
    "WHERE latest.finance_import_row_id=fir.id) "
    "LEFT JOIN client_ledger_entries ledger ON ledger.finance_import_row_id=fir.id "
    "WHERE COALESCE(classification.classification_type,fir.classification_type) "
    "IN ('client_receipt','client_refund','client_subsidy_return') "
    "AND (JSON_CONTAINS(classification.target_identities,"
    "JSON_QUOTE(CONCAT('client:',selected_order.client_id))) "
    "OR JSON_CONTAINS(classification.target_identities,JSON_QUOTE(selected_order.case_no))) "
    "AND fir.reconciliation_status='pending' AND fir.transaction_date IS NOT NULL "
    "AND ledger.id IS NULL ORDER BY fir.id"
)
_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,result_snapshot FROM client_finance_apply_receipts "
    "WHERE idempotency_key=%s FOR UPDATE"
)
_EVENT_INSERT_SQL = (
    "INSERT INTO historical_client_payment_events "
    "(event_identity,case_no,direction,confirmation_kind,payer_role,payee_role,"
    "payment_date,payment_date_unknown_reason,source_availability,evidence_reference,"
    "historical_adoption_receipt_id,expected_account_version,resulting_account_version,"
    "idempotency_key,actor_id,reason,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_LINK_INSERT_SQL = (
    "INSERT INTO historical_client_payment_obligation_links "
    "(event_id,obligation_identity,amount_snapshot_ntd,obligation_type,"
    "obligation_direction,obligation_projection_version,link_ordinal) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s)"
)
_PROJECTION_UPSERT_SQL = (
    "INSERT INTO historical_client_payment_projections "
    "(obligation_identity,case_no,current_event_id,confirmation_kind,amount_snapshot_ntd,"
    "obligation_projection_version,account_version) VALUES (%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE case_no=VALUES(case_no),current_event_id=VALUES(current_event_id),"
    "confirmation_kind=VALUES(confirmation_kind),amount_snapshot_ntd=VALUES(amount_snapshot_ntd),"
    "obligation_projection_version=VALUES(obligation_projection_version),account_version=VALUES(account_version)"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO historical_client_payment_source_outbox "
    "(event_id,intent_key,payload_snapshot) VALUES (%s,%s,%s)"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO client_finance_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "resulting_account_version,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s)"
)


__all__ = ["HistoricalClientPaymentMySqlUnitOfWork", "MySqlHistoricalClientPaymentRepository"]
