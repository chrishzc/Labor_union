"""MySQL persistence for typed historical Finance Import reprocess."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportDisposition,
)
from domains.finance_import.transaction_classifier import classify_finance_transaction
from infrastructure.mysql.finance_import_repository import (
    _batch_database_id,
    _canonical_json,
    _mysql_cursor,
    _row_database_id,
)
from scripts.imports.finance_normalized_row import validate_normalized_row
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from subsystems.finance_import.historical_reprocess_workflow import (
    HistoricalReprocessFacts,
    HistoricalReprocessReceipt,
    HistoricalReprocessRow,
    HistoricalOwnerSelection,
    StoredHistoricalReprocessReceipt,
)
from subsystems.finance_import.identity_maps import load_finance_identity_maps


class MySqlHistoricalReprocessRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load_historical_reprocess(self, batch_identity, *, for_update, owner_selections=()):
        with _mysql_cursor(self._connection) as cursor:
            header = _load_header(cursor, batch_identity, for_update)
            rows = _load_rows(cursor, int(header["batch_id"]), for_update)
            maps = load_finance_identity_maps(cursor)
            _validate_owner_selections(rows, owner_selections)
            planned_rows = tuple(
                _reprocess_row(cursor, row, maps, _selection_for_row(owner_selections, row))
                for row in rows
            )
        return HistoricalReprocessFacts(
            str(header["batch_identity"]), int(header["batch_version"]),
            str(header["status"]) == "completed", str(header["classifier_version"]),
            planned_rows,
        )

    def append_owner_selection_events(self, plan, request):
        batch_id = _batch_database_id(plan.batch_identity)
        with _mysql_cursor(self._connection) as cursor:
            for row in plan.rows:
                selection = row.owner_selection
                if selection is None:
                    continue
                cursor.execute(
                    _OWNER_SELECTION_INSERT_SQL,
                    (
                        _row_database_id(row.row_identity),
                        batch_id,
                        selection.case_no,
                        selection.obligation_identity,
                        request.actor.actor_id,
                        selection.reason,
                        _canonical_json(selection.evidence_references),
                        row.after.canonical_fact_version - 1,
                        row.after.canonical_fact_version,
                        request.expected_batch_version.value,
                        _obligation_projection_version(cursor, selection),
                        request.preview_fingerprint.value,
                        request.idempotency_key.value,
                    ),
                )

    def find_historical_reprocess_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def append_reprocess_classification_events(self, plan, actor):
        batch_id = _batch_database_id(plan.batch_identity)
        with _mysql_cursor(self._connection) as cursor:
            for row in plan.rows:
                cursor.execute(_CLASSIFICATION_INSERT_SQL, _classification_values(batch_id, row, actor.actor_id))

    def append_reprocess_run(self, plan, dispatched_count, actor):
        batch_id = _batch_database_id(plan.batch_identity)
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _RUN_INSERT_SQL,
                _run_values(batch_id, plan, dispatched_count, actor.actor_id),
            )
            run_id = int(cursor.lastrowid or 0)
        if run_id < 1:
            raise RuntimeError("historical_reprocess_run_not_created")
        return run_id

    def append_reprocess_outbox(self, plan):
        batch_id = _batch_database_id(plan.batch_identity)
        payload = {"batch_identity": plan.batch_identity, "plan_fingerprint": plan.fingerprint.value, "row_identities": tuple(row.row_identity for row in plan.rows)}
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_OUTBOX_INSERT_SQL, (batch_id, f"historical-reprocess:{plan.fingerprint.value}", _canonical_json(payload)))

    def advance_batch_version(self, batch_identity, expected_version, resulting_version):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_BATCH_VERSION_UPDATE_SQL, (resulting_version, batch_identity, expected_version))
            if cursor.rowcount != 1:
                raise RuntimeError("stale_preview")

    def save_historical_reprocess_receipt(self, key, stored):
        receipt = stored.receipt
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_INSERT_SQL, (key.value, stored.command_fingerprint.value, receipt.fingerprint.value, _batch_database_id(receipt.batch_identity), receipt.reprocess_run_id, _canonical_json(_receipt_payload(receipt))))


def _load_header(cursor, batch_identity, for_update):
    cursor.execute(_HEADER_SQL + (" FOR UPDATE" if for_update else ""), (batch_identity,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError("finance_import_batch_not_found")
    return row


def _load_rows(cursor, batch_id, for_update):
    cursor.execute(_ROWS_SQL + (" FOR UPDATE" if for_update else ""), (batch_id,))
    return tuple(cursor.fetchall())


def _reprocess_row(cursor, row, maps, owner_selection):
    if owner_selection is not None:
        return _manual_owner_row(cursor, row, owner_selection)
    normalized = validate_normalized_row(_normalized_row(row))
    decision = classify_finance_transaction(normalized, maps["client_refund_accounts"], maps["staff_accounts"], maps.get("client_subsidy_return_accounts", {}), maps.get("client_receipt_candidates", ()))
    classification = FinanceClassificationType(str(decision["classification_type"]))
    if classification is FinanceClassificationType.NON_BUSINESS_REVIEW:
        raise ValueError("reprocess_owner_not_resolved")
    row_identity = f"finance-import-row:{int(row['id'])}"
    after = CanonicalFinanceImportRow(row_identity, int(row["canonical_fact_version"]) + 1, MoneyNTD(_amount(row)), classification, FinanceImportDisposition.BUSINESS_PENDING, fingerprint_payload({"row": row_identity, "classification": classification.value, "reason": decision["reason"]}), _target_identities(classification, decision["matched_identity_ids"]), (str(decision["reason"]),), ("historical_reprocess_apply",))
    return HistoricalReprocessRow(row_identity, FinanceClassificationType.NON_BUSINESS_REVIEW, after)


def _manual_owner_row(cursor, row, selection):
    obligation_projection_version = _require_open_refund_obligation(
        cursor,
        selection,
        _amount(row),
    )
    row_identity = f"finance-import-row:{int(row['id'])}"
    after = CanonicalFinanceImportRow(
        row_identity,
        int(row["canonical_fact_version"]) + 1,
        MoneyNTD(_amount(row)),
        FinanceClassificationType.CLIENT_REFUND,
        FinanceImportDisposition.BUSINESS_PENDING,
        fingerprint_payload({
            "row": row_identity,
            "case_no": selection.case_no,
            "obligation": selection.obligation_identity,
            "evidence": selection.evidence_references,
            "obligation_projection_version": obligation_projection_version,
        }),
        (selection.obligation_identity,),
        tuple(sorted(set((*selection.evidence_references, "historical_owner_selection")))),
        ("historical_reprocess_apply",),
    )
    return HistoricalReprocessRow(
        row_identity,
        FinanceClassificationType.NON_BUSINESS_REVIEW,
        after,
        selection,
    )


def _validate_owner_selections(rows, selections):
    eligible = tuple(f"finance-import-row:{int(row['id'])}" for row in rows)
    selected = tuple(item.row_identity for item in selections)
    if selected != tuple(sorted(set(selected))):
        raise ValueError("historical_owner_selection_duplicate")
    if any(identity not in eligible for identity in selected):
        raise ValueError("historical_owner_selection_not_eligible")


def _selection_for_row(selections, row):
    identity = f"finance-import-row:{int(row['id'])}"
    return next((item for item in selections if item.row_identity == identity), None)


def _require_open_refund_obligation(cursor, selection, amount):
    cursor.execute(
        "SELECT projection_version FROM client_obligations "
        "WHERE obligation_identity=%s AND case_no=%s "
        "AND direction='payable_to_client' AND status='open' "
        "AND obligation_type IN ('refund','adjustment') AND amount_due_ntd=%s FOR UPDATE",
        (selection.obligation_identity, selection.case_no, amount),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("historical_owner_obligation_not_open_or_exact")
    return int(row["projection_version"])


def _obligation_projection_version(cursor, selection):
    cursor.execute(
        "SELECT projection_version FROM client_obligations "
        "WHERE obligation_identity=%s AND case_no=%s AND status='open' FOR UPDATE",
        (selection.obligation_identity, selection.case_no),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("historical_owner_obligation_not_open_or_exact")
    return int(row["projection_version"])


def _normalized_row(row):
    values = {name: row.get(name) for name in (
        "format_id", "source_file", "source_bank_account", "sheet_name", "source_row", "source_reference", "transaction_date", "transaction_time", "posting_date", "value_date", "debit", "credit", "direction", "balance", "currency", "summary", "memo", "counterparty_name", "counterparty_account", "cancellation_code", "bank_references", "warnings", "raw_payload"
    )}
    for field, expected in (("bank_references", dict), ("warnings", list), ("raw_payload", dict)):
        values[field] = _json_value(values[field], expected)
    for field in ("transaction_date", "transaction_time", "posting_date", "value_date"):
        values[field] = _iso_value(values[field])
    return values


def _target_identities(classification, identifiers):
    if classification is FinanceClassificationType.GOVERNMENT_SUBSIDY:
        raise ValueError("reprocess_government_subsidy_target_required")
    prefix = "staff:" if classification is FinanceClassificationType.STAFF_PAYOUT else "client:"
    return tuple(f"{prefix}{item}" for item in sorted(set(int(item) for item in identifiers)))


def _amount(row):
    value = row.get("credit") or row.get("debit")
    amount = int(value)
    if amount < 1 or amount != value:
        raise ValueError("bank_amount_must_be_positive_integer_ntd")
    return amount


def _classification_values(batch_id, row, actor):
    after = row.after
    return (batch_id, _row_database_id(row.row_identity), after.canonical_fact_version, after.canonical_fact_version, after.classification_type.value, after.disposition.value, after.decision_facts_fingerprint.value, _canonical_json(after.target_identities), _canonical_json(after.evidence), _canonical_json(after.available_actions), actor, "historical_reprocess")


def _run_values(batch_id, plan, dispatched_count, actor):
    summary = {"row_identities": tuple(row.row_identity for row in plan.rows), "plan_fingerprint": plan.fingerprint.value}
    return (batch_id, "completed", actor, "historical_reprocess:v1", plan.fingerprint.value, len(plan.rows), len(plan.rows), dispatched_count, dispatched_count, 0, _canonical_json(summary), _canonical_json(summary))


def _stored_receipt(row):
    payload = json.loads(row["result_snapshot"])
    receipt = HistoricalReprocessReceipt(str(payload["batch_identity"]), int(payload["resulting_batch_version"]), int(payload["reprocess_run_id"]), int(payload["reclassified_count"]), int(payload["dispatched_count"]), PreviewFingerprint(str(payload["fingerprint"])))
    return StoredHistoricalReprocessReceipt(PreviewFingerprint(str(row["command_fingerprint"])), receipt)


def _receipt_payload(receipt):
    return {"batch_identity": receipt.batch_identity, "resulting_batch_version": receipt.resulting_batch_version, "reprocess_run_id": receipt.reprocess_run_id, "reclassified_count": receipt.reclassified_count, "dispatched_count": receipt.dispatched_count, "fingerprint": receipt.fingerprint.value}


def _json_value(value, expected):
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, expected):
        raise ValueError("historical_reprocess_row_json_invalid")
    return decoded


def _iso_value(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        if not 0 <= total_seconds < 24 * 60 * 60:
            raise ValueError("historical_reprocess_time_out_of_range")
        hours, remainder = divmod(total_seconds, 60 * 60)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return value


_HEADER_SQL = "SELECT contract.batch_id,contract.batch_identity,contract.batch_version,contract.classifier_version,batch.status FROM finance_import_batch_contracts contract JOIN finance_import_batches batch ON batch.id=contract.batch_id WHERE contract.batch_identity=%s AND batch.status='completed'"
_ROWS_SQL = "SELECT bank_row.*,classification.canonical_fact_version FROM finance_import_rows bank_row JOIN finance_import_occurrences occurrence ON occurrence.finance_import_row_id=bank_row.id JOIN finance_import_classification_events classification ON classification.id=(SELECT MAX(latest.id) FROM finance_import_classification_events latest WHERE latest.finance_import_row_id=bank_row.id) WHERE occurrence.batch_id=%s AND classification.classification_type='non_business_review' AND bank_row.reconciliation_status='pending' ORDER BY bank_row.id"
_CLASSIFICATION_INSERT_SQL = "INSERT INTO finance_import_classification_events(batch_id,finance_import_row_id,classification_version,canonical_fact_version,classification_type,disposition,decision_facts_fingerprint,target_identities,evidence,available_actions,actor,reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
_RUN_INSERT_SQL = "INSERT INTO finance_import_reprocess_runs(batch_id,batch_status,actor,classifier_version,plan_fingerprint,selected_count,changed_count,dispatch_count,reconciled_count,pending_count,request_summary,result_summary) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
_OUTBOX_INSERT_SQL = "INSERT INTO finance_import_outbox(batch_id,intent_key,intent_type,payload_snapshot) VALUES (%s,%s,'historical_reprocess_completed',%s)"
_BATCH_VERSION_UPDATE_SQL = "UPDATE finance_import_batch_contracts SET batch_version=%s WHERE batch_identity=%s AND batch_version=%s"
_RECEIPT_SELECT_SQL = "SELECT command_fingerprint,result_snapshot FROM finance_import_historical_reprocess_receipts WHERE idempotency_key=%s FOR UPDATE"
_RECEIPT_INSERT_SQL = "INSERT INTO finance_import_historical_reprocess_receipts(idempotency_key,command_fingerprint,preview_fingerprint,batch_id,reprocess_run_id,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s)"
_OWNER_SELECTION_INSERT_SQL = "INSERT INTO historical_owner_selection_events(finance_import_row_id,batch_id,case_no,obligation_identity,actor,reason,evidence_references,source_canonical_fact_version,resulting_canonical_fact_version,batch_version,obligation_projection_version,preview_fingerprint,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
