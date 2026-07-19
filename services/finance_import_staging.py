"""Persist normalized bank rows and classification results into raw staging."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import json
from typing import Any, Mapping

from services.finance_transaction_classifier import classify_finance_transaction
from services.finance_transaction_fingerprint import build_dedup_fingerprint


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        converted = item()
        if isinstance(converted, Decimal):
            return str(converted)
        if isinstance(converted, (datetime, date, time)):
            return converted.isoformat()
        if isinstance(converted, (str, int, float, bool)) or converted is None:
            return converted
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=_json_default,
    )


def _identity_maps(identity_maps: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if not isinstance(identity_maps, Mapping):
        raise ValueError("identity_maps must be a mapping")
    client_accounts = identity_maps.get("client_refund_accounts", {})
    staff_accounts = identity_maps.get("staff_accounts", {})
    if not isinstance(client_accounts, Mapping) or not isinstance(staff_accounts, Mapping):
        raise ValueError("identity account maps must be mappings")
    return client_accounts, staff_accounts


def stage_finance_rows(
    cursor: Any,
    normalized_result: Mapping[str, Any],
    identity_maps: Mapping[str, Any],
) -> dict[str, Any]:
    """Stage every normalized row before classification; never commit or reconcile."""
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    if not isinstance(normalized_result, Mapping):
        raise ValueError("normalized_result must be a mapping")
    rows = normalized_result.get("normalized_rows")
    if not isinstance(rows, list):
        raise ValueError("normalized_rows must be a list")
    format_id = normalized_result.get("format_id")
    sheet_name = normalized_result.get("sheet_name")
    header_row = normalized_result.get("header_row")
    if format_id not in {"legacy", "taishin", "sinopac"}:
        raise ValueError("normalized_result has an unsupported format_id")
    if not isinstance(sheet_name, str) or not sheet_name:
        raise ValueError("normalized_result must include sheet_name")
    if not isinstance(header_row, int) or isinstance(header_row, bool) or header_row < 1:
        raise ValueError("normalized_result must include a positive header_row")
    client_accounts, staff_accounts = _identity_maps(identity_maps)

    source_files = {row.get("source_file") for row in rows if isinstance(row, Mapping)}
    source_file = next(iter(source_files)) if len(source_files) == 1 else None
    cursor.execute(
        """INSERT INTO finance_import_batches
           (format_id, source_file, sheet_name, header_row, row_count, status)
           VALUES (%s,%s,%s,%s,%s,'staged')""",
        (format_id, source_file, sheet_name, header_row, len(rows)),
    )
    batch_id = cursor.lastrowid
    if not batch_id:
        raise RuntimeError("finance import batch id was not generated")

    staged_rows = []
    fingerprints_in_batch: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each normalized row must be a mapping")
        if row.get("format_id") != format_id or row.get("sheet_name") != sheet_name:
            raise ValueError("normalized row metadata does not match its batch")

        dedup_fingerprint = build_dedup_fingerprint(row)
        cursor.execute(
            """SELECT id, classification_type, reconciliation_status
               FROM finance_import_rows
               WHERE dedup_fingerprint=%s""",
            (dedup_fingerprint,),
        )
        existing = cursor.fetchone()
        duplicate_in_batch = dedup_fingerprint in fingerprints_in_batch
        fingerprints_in_batch.add(dedup_fingerprint)

        if existing is not None:
            if not isinstance(existing, Mapping):
                raise TypeError("cursor must return mapping rows")
            occurrence_warnings = list(row.get("warnings") or [])
            if duplicate_in_batch and "duplicate_fingerprint_in_same_batch" not in occurrence_warnings:
                occurrence_warnings.append("duplicate_fingerprint_in_same_batch")
            cursor.execute(
                """INSERT INTO finance_import_occurrences (
                       batch_id, finance_import_row_id, source_file,
                       sheet_name, source_row, warnings
                   ) VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    batch_id,
                    existing["id"],
                    row.get("source_file"),
                    row.get("sheet_name"),
                    row.get("source_row"),
                    _json(occurrence_warnings),
                ),
            )
            staged_rows.append(
                {
                    "row_id": existing["id"],
                    "dedup_fingerprint": dedup_fingerprint,
                    "classification_type": existing["classification_type"],
                    "reconciliation_status": existing["reconciliation_status"],
                    "result": "skipped_existing",
                }
            )
            continue

        cursor.execute(
            """INSERT INTO finance_import_rows (
                   dedup_fingerprint, batch_id, format_id, source_file, source_bank_account,
                   sheet_name, source_row, source_reference,
                   transaction_date, transaction_time, posting_date, value_date,
                   debit, credit, direction, balance, currency,
                   summary, memo, counterparty_name, counterparty_account,
                   cancellation_code, bank_references, warnings, raw_payload,
                   reconciliation_status
                ) VALUES (
                   %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                   %s,%s,%s,%s,%s,%s,%s,%s,%s,'pending'
                )""",
            (
                dedup_fingerprint,
                batch_id,
                row.get("format_id"),
                row.get("source_file"),
                row.get("source_bank_account"),
                row.get("sheet_name"),
                row.get("source_row"),
                row.get("source_reference"),
                row.get("transaction_date"),
                row.get("transaction_time"),
                row.get("posting_date"),
                row.get("value_date"),
                row.get("debit"),
                row.get("credit"),
                row.get("direction"),
                row.get("balance"),
                row.get("currency"),
                row.get("summary"),
                row.get("memo"),
                row.get("counterparty_name"),
                row.get("counterparty_account"),
                row.get("cancellation_code"),
                _json(row.get("bank_references")),
                _json(row.get("warnings")),
                _json(row.get("raw_payload")),
            ),
        )
        staged_row_id = cursor.lastrowid
        if not staged_row_id:
            raise RuntimeError("finance import row id was not generated")

        cursor.execute(
            """INSERT INTO finance_import_occurrences (
                   batch_id, finance_import_row_id, source_file,
                   sheet_name, source_row, warnings
               ) VALUES (%s,%s,%s,%s,%s,%s)""",
            (
                batch_id,
                staged_row_id,
                row.get("source_file"),
                row.get("sheet_name"),
                row.get("source_row"),
                _json(row.get("warnings")),
            ),
        )

        classification = classify_finance_transaction(
            row,
            client_accounts,
            staff_accounts,
        )
        classification_type = classification["classification_type"]
        matched_identity_ids = classification.get("matched_identity_ids", [])
        resolved_counterparty_account = classification.get("resolved_counterparty_account")
        reason = classification.get("reason")
        cursor.execute(
            """UPDATE finance_import_rows
               SET classification_type=%s,
                   matched_identity_ids=%s,
                   resolved_counterparty_account=%s,
                   classification_reason=%s
               WHERE id=%s""",
            (
                classification_type,
                _json(matched_identity_ids),
                resolved_counterparty_account,
                reason,
                staged_row_id,
            ),
        )
        staged_rows.append(
            {
                "row_id": staged_row_id,
                "dedup_fingerprint": dedup_fingerprint,
                "classification_type": classification_type,
                "resolved_counterparty_account": resolved_counterparty_account,
                "reconciliation_status": "pending",
                "result": "inserted",
            }
        )

    return {"batch_id": batch_id, "staged_rows": staged_rows}
