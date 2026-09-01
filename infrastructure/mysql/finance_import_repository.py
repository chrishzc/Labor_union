"""MySQL adapter for Finance Import Preview, Apply, and manual correction."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import hashlib
import json
from typing import Iterator

from pymysql.err import OperationalError

from domains.finance_import.correction import (
    CorrectionTargetObligation,
    FinanceImportCorrectionFacts,
    FinanceImportCorrectionSelection,
    FinanceOwningDomain,
)
from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportBatchFacts,
    FinanceImportDisposition,
)
from domains.client_finance.refund_return_review import (
    RefundReturnReviewFacts,
    RefundReturnReviewSelection,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.anomaly_registry_repository import (
    append_finance_import_manual_review_resolution,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.finance_import.correction_workflow import (
    FinanceImportCorrectionReceipt,
    StoredFinanceImportCorrectionReceipt,
)
from subsystems.finance_import.import_workflow import (
    FinanceDispatchOutcome,
    FinanceImportApplyReceipt,
    FinanceImportRepositoryUnavailable,
    StoredFinanceImportReceipt,
)
from subsystems.finance_import.refund_return_review_workflow import (
    RefundReturnReviewReceipt,
    StoredRefundReturnReviewReceipt,
)

_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class FinanceImportMySqlUnitOfWork(MySqlUnitOfWork):
    def __enter__(self):
        try:
            return super().__enter__()
        except OperationalError as error:
            _raise_transient_repository_error(error)
            raise

    def commit(self) -> None:
        try:
            super().commit()
        except OperationalError as error:
            _raise_transient_repository_error(error)
            raise


class MySqlFinanceImportRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, identity_or_selection, *, for_update):
        with _mysql_cursor(self._connection) as cursor:
            if isinstance(identity_or_selection, FinanceImportCorrectionSelection):
                return _load_correction_facts(
                    cursor,
                    identity_or_selection,
                    for_update,
                )
            return _load_batch_facts(
                cursor,
                str(identity_or_selection),
                for_update,
            )

    def find_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_APPLY_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_apply_receipt(row)

    def append_dispatch_audit(self, plan, results) -> None:
        batch_id = _batch_database_id(plan.batch_identity)
        result_by_row = {result.row_identity: result for result in results}
        with _mysql_cursor(self._connection) as cursor:
            for candidate in plan.dispatchable_rows:
                result = result_by_row[candidate.row_identity]
                cursor.execute(
                    _DISPATCH_INSERT_SQL,
                    (
                        batch_id,
                        _row_database_id(candidate.row_identity),
                        plan.fingerprint.value,
                        result.outcome.value,
                        result.result_reference,
                    ),
                )

    def append_outbox(self, plan_or_candidate, results=None) -> None:
        if results is None:
            self._append_correction_outbox(plan_or_candidate)
            return
        plan = plan_or_candidate
        payload = {
            "batch_identity": plan.batch_identity,
            "plan_fingerprint": plan.fingerprint.value,
            "results": tuple(_dispatch_payload(item) for item in results),
        }
        self._insert_outbox(
            _batch_database_id(plan.batch_identity),
            _hashed_identity("finance-import-dispatch", plan.fingerprint.value),
            "dispatch_completed",
            payload,
        )

    # Kept whole so the aggregate version compare-and-swap remains auditable.
    def advance_batch_version(
        self,
        batch_or_candidate,
        expected_version,
        resulting_version,
    ) -> None:
        batch_identity = getattr(
            batch_or_candidate,
            "batch_identity",
            batch_or_candidate,
        )
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _BATCH_VERSION_UPDATE_SQL,
                (
                    resulting_version,
                    batch_identity,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("stale_preview")

    def save_receipt(self, key, stored) -> None:
        receipt = stored.receipt
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _APPLY_RECEIPT_INSERT_SQL,
                (
                    key.value,
                    stored.command_fingerprint.value,
                    receipt.preview_fingerprint.value,
                    _batch_database_id(receipt.batch_identity),
                    _canonical_json(_apply_receipt_payload(receipt)),
                ),
            )

    def find_correction_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_CORRECTION_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_correction_receipt(row)

    def load_refund_return_review(self, selection, *, for_update):
        if not isinstance(selection, RefundReturnReviewSelection):
            raise TypeError("refund return review selection is required")
        row_id = _row_database_id(selection.row_identity)
        ledger_id = _ledger_database_id(
            selection.original_refund_ledger_entry_identity
        )
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _REFUND_RETURN_REVIEW_FACTS_SQL + (" FOR UPDATE" if for_update else ""),
                (ledger_id, row_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise ValueError("refund_return_review_target_not_found")
        return RefundReturnReviewFacts(
            str(row["batch_identity"]),
            int(row["batch_version"]),
            MoneyNTD(_integer_bank_amount(row["credit"], row["debit"])),
            _refund_return_bank_row_is_pending_credit(row),
            MoneyNTD(int(row["original_refund_amount_ntd"])),
            _original_refund_is_open(row),
            str(row["original_refund_case_no"]),
        )

    def find_refund_return_review_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_REFUND_RETURN_REVIEW_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_refund_return_review_receipt(row)

    def append_refund_return_review(self, candidate, request):
        selection = candidate.selection
        row_id = _row_database_id(selection.row_identity)
        ledger_id = _ledger_database_id(
            selection.original_refund_ledger_entry_identity
        )
        batch_id = _batch_database_id(candidate.batch_identity)
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _REFUND_RETURN_REVIEW_EVENT_INSERT_SQL,
                (
                    row_id,
                    ledger_id,
                    selection.case_no,
                    selection.reason,
                    _canonical_json(selection.evidence),
                    request.actor.actor_id,
                    request.correlation_id.value,
                    request.idempotency_key.value,
                ),
            )
            event_id = int(cursor.lastrowid)
            event_identity = f"client-refund-return-review:{event_id}"
            payload = _refund_return_review_outbox_payload(
                cursor,
                candidate,
                event_identity,
                event_id,
            )
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                (
                    batch_id,
                    _hashed_identity(
                        "refund-return-review",
                        candidate.fingerprint.value,
                    ),
                    "refund_return_review_recorded",
                    _canonical_json(payload),
                ),
            )
        return event_identity

    def save_refund_return_review_receipt(self, key, stored):
        receipt = stored.receipt
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _REFUND_RETURN_REVIEW_RECEIPT_INSERT_SQL,
                (
                    key.value,
                    stored.command_fingerprint.value,
                    _row_database_id(receipt.row_identity),
                    _review_event_database_id(receipt.review_event_identity),
                    _canonical_json(_refund_return_review_receipt_payload(receipt)),
                ),
            )

    # Kept whole so one immutable decision event carries its complete evidence.
    def append_manual_classification(self, candidate, actor) -> None:
        row_id = _row_database_id(candidate.row_identity)
        batch_id = _batch_database_id(candidate.batch_identity)
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_CLASSIFICATION_VERSION_SQL, (row_id,))
            current = cursor.fetchone()
            cursor.execute(
                _CLASSIFICATION_INSERT_SQL,
                (
                    batch_id,
                    row_id,
                    int(current["next_classification_version"]),
                    int(current["canonical_fact_version"]),
                    candidate.classification_type.value,
                    candidate.fingerprint.value,
                    _canonical_json(
                        tuple(
                            item.obligation_identity
                            for item in candidate.allocations
                        )
                    ),
                    _canonical_json(candidate.evidence),
                    actor.actor_id,
                    candidate.reason,
                ),
            )

    def append_reconciliation_receipt(self, candidate) -> None:
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _RECONCILIATION_RECEIPT_INSERT_SQL,
                (
                    _row_database_id(candidate.row_identity),
                    candidate.fingerprint.value,
                    candidate.owning_domain.value,
                    len(candidate.allocations),
                    candidate.bank_amount.amount,
                ),
            )

    def append_alert_resolved_event(self, candidate, actor) -> int:
        return append_finance_import_manual_review_resolution(
            self._connection,
            candidate,
            actor,
        )

    def _append_correction_outbox(self, candidate) -> None:
        payload = {
            "row_identity": candidate.row_identity,
            "batch_identity": candidate.batch_identity,
            "candidate_fingerprint": candidate.fingerprint.value,
            "owning_domain": candidate.owning_domain.value,
            "classification_type": candidate.classification_type.value,
            "refund_ledger_entry_identity": candidate.refund_ledger_entry_identity,
        }
        self._insert_outbox(
            _batch_database_id(candidate.batch_identity),
            _hashed_identity("finance-import-correction", candidate.fingerprint.value),
            "manual_correction_completed",
            payload,
        )

    def save_correction_receipt(self, key, stored) -> None:
        receipt = stored.receipt
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _CORRECTION_RECEIPT_INSERT_SQL,
                (
                    key.value,
                    stored.command_fingerprint.value,
                    receipt.preview_fingerprint.value,
                    _row_database_id(receipt.row_identity),
                    _canonical_json(_correction_receipt_payload(receipt)),
                ),
            )

    def _insert_outbox(self, batch_id, intent_key, intent_type, payload):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                (
                    batch_id,
                    intent_key,
                    intent_type,
                    _canonical_json(payload),
                ),
            )


# Kept whole so every Preview fact comes from one consistent batch snapshot.
def _load_batch_facts(cursor, batch_identity, for_update):
    cursor.execute(
        _BATCH_HEADER_SQL + (" FOR UPDATE" if for_update else ""),
        (batch_identity,),
    )
    header = cursor.fetchone()
    if header is None:
        raise ValueError("finance_import_batch_not_found")
    cursor.execute(
        _BATCH_COUNTS_SQL,
        (header["batch_id"], header["batch_id"], header["batch_id"]),
    )
    counts = cursor.fetchone()
    cursor.execute(
        _BATCH_ROWS_SQL,
        (header["batch_id"], header["batch_id"]),
    )
    raw_rows = tuple(cursor.fetchall())
    if len(raw_rows) != int(counts["canonical_member_count"]):
        raise ValueError("classification_event_missing")
    issues = _load_integrity_issues(cursor, int(header["batch_id"]))
    rows = tuple(_canonical_row(row, issues) for row in raw_rows)
    return FinanceImportBatchFacts(
        str(header["batch_identity"]),
        int(header["batch_version"]),
        int(header["row_count"]),
        int(counts["canonical_created_count"]),
        int(counts["duplicate_occurrence_count"]),
        str(header["source_content_digest"]),
        str(header["classifier_version"]),
        str(header["fingerprint_version"]),
        rows,
        str(header["status"]) == "completed",
        issues.get(None, ()),
    )


# Kept whole so no mutable raw bank field leaks into the canonical row contract.
def _canonical_row(row, issues):
    row_id = int(row["finance_import_row_id"])
    amount = _integer_bank_amount(row["credit"], row["debit"])
    violations = issues.get(row_id, ())
    return CanonicalFinanceImportRow(
        _row_identity(row_id),
        int(row["canonical_fact_version"]),
        MoneyNTD(amount),
        FinanceClassificationType(str(row["classification_type"])),
        FinanceImportDisposition(str(row["disposition"])),
        PreviewFingerprint(str(row["decision_facts_fingerprint"])),
        _json_text_tuple(row["target_identities"]),
        _json_text_tuple(row["evidence"]),
        _json_text_tuple(row["available_actions"]),
        tuple(
            code
            for code in violations
            if code not in {"fingerprint_collision", "formal_reference_conflict"}
        ),
        "fingerprint_collision" in violations,
        "formal_reference_conflict" in violations,
    )


def _load_integrity_issues(cursor, batch_id):
    cursor.execute(_ACTIVE_INTEGRITY_SQL, (batch_id,))
    issues: dict[int | None, list[str]] = {}
    for row in cursor.fetchall():
        row_id = row["finance_import_row_id"]
        key = None if row_id is None else int(row_id)
        issues.setdefault(key, []).append(str(row["issue_code"]))
    return {key: tuple(sorted(set(values))) for key, values in issues.items()}


# Kept whole so row, classification, obligations, and blockers share one lock snapshot.
def _load_correction_facts(cursor, selection, for_update):
    row_id = _row_database_id(selection.row_identity)
    cursor.execute(
        _CORRECTION_HEADER_SQL + (" FOR UPDATE" if for_update else ""),
        (row_id,),
    )
    header = cursor.fetchone()
    if header is None:
        raise ValueError("finance_import_row_not_found")
    obligations = _load_obligations(cursor, selection, for_update)
    issues = _load_integrity_issues(cursor, int(header["batch_id"]))
    row_issues = issues.get(row_id, ())
    return FinanceImportCorrectionFacts(
        str(header["batch_identity"]),
        int(header["batch_version"]),
        int(header["canonical_fact_version"]),
        int(header["classification_version"]),
        MoneyNTD(_integer_bank_amount(header["credit"], header["debit"])),
        str(header["disposition"]) == "manual_review",
        obligations,
        tuple(
            code
            for code in row_issues
            if code not in {"fingerprint_collision", "formal_reference_conflict"}
        ),
        "fingerprint_collision" in row_issues,
        "formal_reference_conflict" in row_issues,
    )


def _load_obligations(cursor, selection, for_update):
    if selection.classification_type is FinanceClassificationType.CLIENT_REFUND_RETURN:
        return _load_refund_return_obligations(cursor, selection, for_update)
    if _is_government_subsidy_correction(selection):
        return _load_government_subsidy_obligations(
            cursor,
            selection.target_obligation_identities,
            for_update,
        )
    return _load_client_and_staff_obligations(
        cursor,
        selection.target_obligation_identities,
        for_update,
    )


def _load_refund_return_obligations(cursor, selection, for_update):
    ledger_id = _database_id(selection.refund_ledger_entry_identity, "")
    placeholders = ",".join(["%s"] * len(selection.target_obligation_identities))
    locking = " FOR UPDATE" if for_update else ""
    cursor.execute(
        "SELECT allocation.obligation_identity,allocation.amount_ntd "
        "FROM client_ledger_entries ledger "
        "JOIN client_ledger_obligation_allocations allocation "
        "ON allocation.ledger_entry_id=ledger.id "
        "WHERE ledger.id=%s AND ledger.entry_type='refund' "
        f"AND allocation.obligation_identity IN ({placeholders}) "
        f"ORDER BY allocation.obligation_identity{locking}",
        (ledger_id, *selection.target_obligation_identities),
    )
    return tuple(
        CorrectionTargetObligation(
            str(row["obligation_identity"]),
            FinanceOwningDomain.CLIENT_FINANCE,
            MoneyNTD(int(row["amount_ntd"])),
        )
        for row in cursor.fetchall()
    )


def _is_government_subsidy_correction(selection):
    return (
        selection.classification_type
        is FinanceClassificationType.GOVERNMENT_SUBSIDY
    )


def _load_government_subsidy_obligations(cursor, identities, for_update):
    placeholders = ",".join(["%s"] * len(identities))
    locking = " FOR UPDATE" if for_update else ""
    statement = _GOVERNMENT_SUBSIDY_OBLIGATIONS_SQL.format(placeholders)
    cursor.execute(statement + locking, identities)
    return tuple(
        _government_subsidy_obligation(row) for row in cursor.fetchall()
    )


def _load_client_and_staff_obligations(cursor, identities, for_update):
    placeholders = ",".join(["%s"] * len(identities))
    locking = " FOR UPDATE" if for_update else ""
    cursor.execute(
        _CLIENT_OBLIGATIONS_SQL.format(placeholders) + locking,
        identities,
    )
    client_rows = tuple(cursor.fetchall())
    cursor.execute(
        _STAFF_OBLIGATIONS_SQL.format(placeholders) + locking,
        identities,
    )
    staff_rows = tuple(cursor.fetchall())
    obligations = tuple(_client_obligation(row) for row in client_rows) + tuple(
        _staff_obligation(row) for row in staff_rows
    )
    return tuple(sorted(obligations, key=lambda item: item.obligation_identity))


def _client_obligation(row):
    return CorrectionTargetObligation(
        str(row["obligation_identity"]),
        FinanceOwningDomain.CLIENT_FINANCE,
        MoneyNTD(int(row["remaining_amount_ntd"])),
    )


def _staff_obligation(row):
    return CorrectionTargetObligation(
        str(row["obligation_identity"]),
        FinanceOwningDomain.STAFF_PAYABLES,
        MoneyNTD(int(row["remaining_amount_ntd"])),
    )


def _government_subsidy_obligation(row):
    return CorrectionTargetObligation(
        str(row["obligation_identity"]),
        FinanceOwningDomain.GOVERNMENT_SUBSIDY,
        MoneyNTD(int(row["remaining_amount_ntd"])),
    )


def _stored_apply_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = FinanceImportApplyReceipt(
        str(payload["batch_identity"]),
        int(payload["resulting_batch_version"]),
        PreviewFingerprint(str(payload["preview_fingerprint"])),
        int(payload["reconciled_count"]),
        int(payload["existing_count"]),
        int(payload["pending_count"]),
    )
    return StoredFinanceImportReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _stored_correction_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = FinanceImportCorrectionReceipt(
        str(payload["row_identity"]),
        str(payload["batch_identity"]),
        int(payload["resulting_batch_version"]),
        int(payload["classification_event_count"]),
        int(payload["ledger_entry_count"]),
        int(payload["allocation_count"]),
        int(payload["reconciliation_receipt_count"]),
        int(payload["alert_resolved_event_count"]),
        PreviewFingerprint(str(payload["preview_fingerprint"])),
    )
    return StoredFinanceImportCorrectionReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _apply_receipt_payload(receipt):
    return {
        "batch_identity": receipt.batch_identity,
        "resulting_batch_version": receipt.resulting_batch_version,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "reconciled_count": receipt.reconciled_count,
        "existing_count": receipt.existing_count,
        "pending_count": receipt.pending_count,
    }


def _correction_receipt_payload(receipt):
    return {
        "row_identity": receipt.row_identity,
        "batch_identity": receipt.batch_identity,
        "resulting_batch_version": receipt.resulting_batch_version,
        "classification_event_count": receipt.classification_event_count,
        "ledger_entry_count": receipt.ledger_entry_count,
        "allocation_count": receipt.allocation_count,
        "reconciliation_receipt_count": receipt.reconciliation_receipt_count,
        "alert_resolved_event_count": receipt.alert_resolved_event_count,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _dispatch_payload(result):
    return {
        "row_identity": result.row_identity,
        "outcome": result.outcome.value,
        "result_reference": result.result_reference,
    }


def _integer_bank_amount(credit, debit):
    amount = Decimal(str(credit or debit or 0))
    if amount <= 0 or amount != amount.to_integral_value():
        raise ValueError("bank_amount_must_be_positive_integer_ntd")
    return int(amount)


def _row_database_id(row_identity):
    return _database_id(row_identity, "finance-import-row:")


def _batch_database_id(batch_identity):
    return _database_id(batch_identity, "finance-import-batch:")


def _database_id(identity, prefix):
    if not isinstance(identity, str) or not identity.startswith(prefix):
        raise ValueError("invalid_finance_import_identity")
    raw_id = identity.removeprefix(prefix)
    if not raw_id.isdigit() or int(raw_id) <= 0:
        raise ValueError("invalid_finance_import_identity")
    return int(raw_id)


def _row_identity(row_id):
    return f"finance-import-row:{row_id}"


def _ledger_database_id(identity):
    return _database_id(identity, "client-ledger-entry:")


def _review_event_database_id(identity):
    return _database_id(identity, "client-refund-return-review:")


def _refund_return_bank_row_is_pending_credit(row):
    return (
        str(row["direction"]) == "incoming"
        and _integer_bank_amount(row["credit"], row["debit"]) > 0
        and str(row["reconciliation_status"]) == "pending"
        and row["bank_ledger_entry_id"] is None
    )


def _original_refund_is_open(row):
    return (
        str(row["original_refund_entry_type"]) == "refund"
        and int(row["refund_reversal_count"]) == 0
    )


def _refund_return_review_outbox_payload(
    cursor,
    candidate,
    event_identity,
    event_id,
):
    selection = candidate.selection
    ledger_id = _ledger_database_id(
        selection.original_refund_ledger_entry_identity
    )
    cursor.execute(_REFUND_LEDGER_ALLOCATIONS_SQL, (ledger_id,))
    obligations = tuple(
        str(row["obligation_identity"])
        for row in cursor.fetchall()
    )
    return {
        "source_event_identity": event_identity,
        "source_version": event_id,
        "row_identity": selection.row_identity,
        "batch_identity": candidate.batch_identity,
        "original_refund_ledger_entry_id": ledger_id,
        "affected_order_identities": (selection.case_no,),
        "affected_obligation_identities": obligations,
    }


def _refund_return_review_receipt_payload(receipt):
    return {
        "review_event_identity": receipt.review_event_identity,
        "row_identity": receipt.row_identity,
        "original_refund_ledger_entry_identity": (
            receipt.original_refund_ledger_entry_identity
        ),
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _stored_refund_return_review_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = RefundReturnReviewReceipt(
        str(payload["review_event_identity"]),
        str(payload["row_identity"]),
        str(payload["original_refund_ledger_entry_identity"]),
        PreviewFingerprint(str(payload["preview_fingerprint"])),
    )
    return StoredRefundReturnReviewReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _hashed_identity(prefix, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_object(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise RuntimeError("Finance Import receipt snapshot must be an object")
    return payload


def _json_text_tuple(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, list):
        raise ValueError("Finance Import classification evidence must be an array")
    return tuple(sorted(str(item) for item in payload))


@contextmanager
def _mysql_cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except OperationalError as error:
        _raise_transient_repository_error(error)
        raise


def _raise_transient_repository_error(error) -> None:
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        raise FinanceImportRepositoryUnavailable(
            "Finance Import MySQL transaction should be retried."
        ) from error


_BATCH_HEADER_SQL = (
    "SELECT contract.batch_id,contract.batch_identity,"
    "contract.source_content_digest,contract.classifier_version,"
    "contract.fingerprint_version,contract.batch_version,batch.row_count,"
    "batch.status FROM finance_import_batch_contracts AS contract "
    "JOIN finance_import_batches AS batch ON batch.id=contract.batch_id "
    "WHERE contract.batch_identity=%s"
)
_BATCH_COUNTS_SQL = (
    "SELECT COUNT(DISTINCT CASE WHEN bank_fact.batch_id=%s "
    "THEN bank_fact.id END) "
    "AS canonical_created_count,"
    "COUNT(DISTINCT occurrence.id)-"
    "COUNT(DISTINCT CASE WHEN bank_fact.batch_id=%s "
    "THEN bank_fact.id END) "
    "AS duplicate_occurrence_count,"
    "COUNT(DISTINCT bank_fact.id) AS canonical_member_count "
    "FROM finance_import_occurrences AS occurrence "
    "JOIN finance_import_rows AS bank_fact "
    "ON bank_fact.id=occurrence.finance_import_row_id "
    "WHERE occurrence.batch_id=%s"
)
_BATCH_ROWS_SQL = (
    "SELECT bank_fact.id AS finance_import_row_id,"
    "bank_fact.credit,bank_fact.debit,"
    "classification.canonical_fact_version,"
    "classification.classification_type,"
    "CASE WHEN bank_fact.batch_id<>%s THEN 'existing' "
    "ELSE classification.disposition END AS disposition,"
    "classification.decision_facts_fingerprint,"
    "classification.target_identities,classification.evidence,"
    "classification.available_actions "
    "FROM finance_import_occurrences AS occurrence "
    "JOIN finance_import_rows AS bank_fact "
    "ON bank_fact.id=occurrence.finance_import_row_id "
    "JOIN finance_import_classification_events AS classification "
    "ON classification.id=("
    "SELECT MAX(latest.id) FROM finance_import_classification_events AS latest "
    "WHERE latest.finance_import_row_id=bank_fact.id"
    ") WHERE occurrence.batch_id=%s "
    "GROUP BY bank_fact.id,bank_fact.credit,bank_fact.debit,classification.id "
    "ORDER BY bank_fact.id"
)
_ACTIVE_INTEGRITY_SQL = (
    "SELECT current.finance_import_row_id,current.issue_code "
    "FROM finance_import_integrity_events AS current "
    "WHERE current.batch_id=%s AND current.id=("
    "SELECT MAX(latest.id) FROM finance_import_integrity_events AS latest "
    "WHERE latest.batch_id=current.batch_id "
    "AND latest.finance_import_row_id<=>current.finance_import_row_id "
    "AND latest.issue_code=current.issue_code"
    ") AND current.active=1 ORDER BY current.finance_import_row_id,current.issue_code"
)
_CORRECTION_HEADER_SQL = (
    "SELECT contract.batch_id,contract.batch_identity,contract.batch_version,"
    "classification.canonical_fact_version,classification.classification_version,"
    "classification.disposition,bank_fact.credit,bank_fact.debit "
    "FROM finance_import_rows AS bank_fact "
    "JOIN finance_import_occurrences AS occurrence "
    "ON occurrence.finance_import_row_id=bank_fact.id "
    "JOIN finance_import_batch_contracts AS contract "
    "ON contract.batch_id=occurrence.batch_id "
    "JOIN finance_import_classification_events AS classification "
    "ON classification.id=("
    "SELECT MAX(latest.id) FROM finance_import_classification_events AS latest "
    "WHERE latest.finance_import_row_id=bank_fact.id"
    ") WHERE bank_fact.id=%s ORDER BY occurrence.id DESC LIMIT 1"
)
_CLIENT_OBLIGATIONS_SQL = (
    "SELECT obligation_identity,amount_due_ntd AS remaining_amount_ntd "
    "FROM client_obligations WHERE status='open' "
    "AND obligation_identity IN ({}) ORDER BY obligation_identity"
)
_STAFF_OBLIGATIONS_SQL = (
    "SELECT obligation_identity,balance_ntd AS remaining_amount_ntd "
    "FROM staff_payable_projections WHERE status IN ('payable','partially_paid') "
    "AND obligation_identity IN ({}) ORDER BY obligation_identity"
)
_GOVERNMENT_SUBSIDY_OBLIGATIONS_SQL = (
    "SELECT CONCAT('government-subsidy-batch:',batch_id) "
    "AS obligation_identity,outstanding_ntd AS remaining_amount_ntd "
    "FROM government_subsidy_batch_accounts "
    "WHERE status IN ('approved','partially_paid') AND outstanding_ntd>0 "
    "AND CONCAT('government-subsidy-batch:',batch_id) IN ({}) ORDER BY batch_id"
)
_APPLY_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,result_snapshot "
    "FROM finance_import_apply_receipts WHERE idempotency_key=%s"
)
_CORRECTION_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,result_snapshot "
    "FROM finance_import_correction_receipts WHERE idempotency_key=%s"
)
_REFUND_RETURN_REVIEW_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,result_snapshot "
    "FROM client_refund_return_review_receipts WHERE idempotency_key=%s"
)
_REFUND_RETURN_REVIEW_FACTS_SQL = (
    "SELECT contract.batch_identity,contract.batch_version,"
    "bank_fact.credit,bank_fact.debit,bank_fact.direction,"
    "bank_fact.reconciliation_status,bank_ledger.id AS bank_ledger_entry_id,"
    "original_refund.case_no AS original_refund_case_no,"
    "original_refund.entry_type AS original_refund_entry_type,"
    "original_refund.amount_ntd AS original_refund_amount_ntd,"
    "COUNT(refund_reversal.id) AS refund_reversal_count "
    "FROM finance_import_rows AS bank_fact "
    "JOIN finance_import_occurrences AS occurrence "
    "ON occurrence.finance_import_row_id=bank_fact.id "
    "JOIN finance_import_batch_contracts AS contract "
    "ON contract.batch_id=occurrence.batch_id "
    "JOIN client_ledger_entries AS original_refund ON original_refund.id=%s "
    "LEFT JOIN client_ledger_entries AS refund_reversal "
    "ON refund_reversal.reversal_of_entry_id=original_refund.id "
    "AND refund_reversal.entry_type='refund_reversal' "
    "LEFT JOIN client_ledger_entries AS bank_ledger "
    "ON bank_ledger.finance_import_row_id=bank_fact.id "
    "WHERE bank_fact.id=%s "
    "GROUP BY contract.batch_identity,contract.batch_version,bank_fact.id,"
    "original_refund.id,bank_ledger.id "
    "ORDER BY MAX(occurrence.id) DESC LIMIT 1"
)
_REFUND_LEDGER_ALLOCATIONS_SQL = (
    "SELECT obligation_identity FROM client_ledger_obligation_allocations "
    "WHERE ledger_entry_id=%s ORDER BY obligation_identity"
)
_DISPATCH_INSERT_SQL = (
    "INSERT INTO finance_import_dispatch_events("
    "batch_id,finance_import_row_id,plan_fingerprint,outcome,result_reference"
    ") VALUES (%s,%s,%s,%s,%s)"
)
_BATCH_VERSION_UPDATE_SQL = (
    "UPDATE finance_import_batch_contracts SET batch_version=%s "
    "WHERE batch_identity=%s AND batch_version=%s"
)
_APPLY_RECEIPT_INSERT_SQL = (
    "INSERT INTO finance_import_apply_receipts("
    "idempotency_key,command_fingerprint,preview_fingerprint,batch_id,"
    "result_snapshot) VALUES (%s,%s,%s,%s,%s)"
)
_CORRECTION_RECEIPT_INSERT_SQL = (
    "INSERT INTO finance_import_correction_receipts("
    "idempotency_key,command_fingerprint,preview_fingerprint,"
    "finance_import_row_id,result_snapshot) VALUES (%s,%s,%s,%s,%s)"
)
_REFUND_RETURN_REVIEW_EVENT_INSERT_SQL = (
    "INSERT INTO client_refund_return_review_events("
    "finance_import_row_id,original_refund_ledger_entry_id,case_no,reason,"
    "evidence,actor,correlation_id,idempotency_key"
    ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
)
_REFUND_RETURN_REVIEW_RECEIPT_INSERT_SQL = (
    "INSERT INTO client_refund_return_review_receipts("
    "idempotency_key,command_fingerprint,finance_import_row_id,review_event_id,"
    "result_snapshot"
    ") VALUES (%s,%s,%s,%s,%s)"
)
_CLASSIFICATION_VERSION_SQL = (
    "SELECT COALESCE(MAX(classification_version),-1)+1 "
    "AS next_classification_version,"
    "MAX(canonical_fact_version) AS canonical_fact_version "
    "FROM finance_import_classification_events "
    "WHERE finance_import_row_id=%s FOR UPDATE"
)
_CLASSIFICATION_INSERT_SQL = (
    "INSERT INTO finance_import_classification_events("
    "batch_id,finance_import_row_id,classification_version,"
    "canonical_fact_version,"
    "classification_type,disposition,decision_facts_fingerprint,"
    "target_identities,evidence,available_actions,actor,reason"
    ") VALUES (%s,%s,%s,%s,%s,'create',%s,%s,%s,JSON_ARRAY(),%s,%s)"
)
_RECONCILIATION_RECEIPT_INSERT_SQL = (
    "INSERT INTO finance_import_reconciliation_receipts("
    "finance_import_row_id,candidate_fingerprint,owning_domain,"
    "allocation_count,amount_ntd) VALUES (%s,%s,%s,%s,%s)"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO finance_import_outbox("
    "batch_id,intent_key,intent_type,payload_snapshot"
    ") VALUES (%s,%s,%s,%s)"
)

__all__ = [
    "FinanceImportMySqlUnitOfWork",
    "MySqlFinanceImportRepository",
]
