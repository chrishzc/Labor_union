"""
File: query.py
Description: 讀取 Finance Import batch、review、reprocess 與已遮罩的 terminal receipt projection。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
from typing import Any


_MAXIMUM_PAGE_SIZE = 100
_REVIEW_DISPOSITIONS = ("manual_review", "business_pending", "blocked")


@dataclass(frozen=True, slots=True)
class FinanceImportBatchSummary:
    batch_id: int
    batch_identity: str | None
    format_id: str
    source_file: str | None
    row_count: int
    status: str
    batch_version: int | None
    architecture_ready: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class FinanceImportBatchManifest:
    batch_id: int
    batch_identity: str
    format_id: str
    source_file: str | None
    sheet_name: str
    header_row: int
    source_row_count: int
    status: str
    batch_version: int
    source_content_digest: str
    classifier_version: str
    fingerprint_version: str
    canonical_row_count: int
    occurrence_count: int
    review_count: int
    dispatch_event_count: int
    reconciliation_receipt_count: int
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class FinanceImportReviewRowSummary:
    row_id: int
    row_identity: str
    transaction_date: date | None
    direction: str
    amount_ntd: int
    classification_type: str
    disposition: str
    reconciliation_status: str
    source_sheet: str
    source_row: int
    occurrence_count: int
    available_actions: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class FinanceImportReprocessRunSummary:
    run_id: int
    batch_identity: str
    classifier_version: str
    plan_fingerprint: str
    selected_count: int
    changed_count: int
    dispatch_count: int
    reconciled_count: int
    pending_count: int
    status: str
    created_at: datetime
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class FinanceImportBatchApplyReceipt:
    """Read-only typed terminal receipt, keyed by the immutable Apply idempotency key."""

    batch_identity: str
    resulting_batch_version: int
    preview_fingerprint: str
    reconciled_count: int
    existing_count: int
    pending_count: int


@dataclass(frozen=True, slots=True)
class FinanceImportCorrectionApplyReceipt:
    """Read-only typed terminal receipt for one durable Finance Import correction."""

    row_identity: str
    batch_identity: str
    resulting_batch_version: int
    classification_event_count: int
    ledger_entry_count: int
    allocation_count: int
    reconciliation_receipt_count: int
    alert_resolved_event_count: int
    preview_fingerprint: str


class FinanceImportQueryNotFound(ValueError):
    """Raised when a formal Finance Import batch does not exist."""


class FinanceImportQueryService:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_batches(
        self, *, limit: int, before_batch_id: int | None = None
    ) -> tuple[FinanceImportBatchSummary, ...]:
        _validate_page(limit, before_batch_id, "before_batch_id")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT batch.id AS batch_id, contract.batch_identity,
                       batch.format_id, batch.source_file, batch.row_count,
                       batch.status, contract.batch_version, batch.created_at
                FROM finance_import_batches AS batch
                LEFT JOIN finance_import_batch_contracts AS contract
                  ON contract.batch_id=batch.id
                WHERE (%s IS NULL OR batch.id<%s)
                ORDER BY batch.id DESC
                LIMIT %s
                """,
                (before_batch_id, before_batch_id, limit),
            )
            rows = tuple(cursor.fetchall())
        return tuple(_batch_summary(row) for row in rows)

    def get_manifest(self, batch_identity: str) -> FinanceImportBatchManifest:
        identity = _canonical_identity(batch_identity)
        row = self._fetch_manifest(identity)
        if row is None:
            raise FinanceImportQueryNotFound("finance import batch was not found")
        return _batch_manifest(row)

    def get_batch_apply_receipt(
        self, idempotency_key: str
    ) -> FinanceImportBatchApplyReceipt | None:
        key = idempotency_key.strip()
        if not key or len(key) > 191:
            raise ValueError("finance_import_apply_receipt_key_invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT result_snapshot FROM finance_import_apply_receipts "
                "WHERE idempotency_key=%s",
                (key,),
            )
            row = cursor.fetchone()
        return None if row is None else _batch_apply_receipt(row)

    def get_correction_apply_receipt(
        self, idempotency_key: str
    ) -> FinanceImportCorrectionApplyReceipt | None:
        key = idempotency_key.strip()
        if not key or len(key) > 191:
            raise ValueError("finance_import_correction_receipt_key_invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT result_snapshot FROM finance_import_correction_receipts "
                "WHERE idempotency_key=%s",
                (key,),
            )
            row = cursor.fetchone()
        return None if row is None else _correction_apply_receipt(row)

    def list_review_rows(
        self,
        batch_identity: str,
        *,
        limit: int,
        after_row_id: int | None = None,
    ) -> tuple[FinanceImportReviewRowSummary, ...]:
        identity = _canonical_identity(batch_identity)
        _validate_page(limit, after_row_id, "after_row_id")
        self._require_formal_batch(identity)
        params = (identity, after_row_id, after_row_id, *_REVIEW_DISPOSITIONS, limit)
        rows = self._fetch_review_rows(params)
        return tuple(_review_row(row) for row in rows)

    def list_reprocess_runs(
        self,
        batch_identity: str,
        *,
        limit: int,
        before_run_id: int | None = None,
    ) -> tuple[FinanceImportReprocessRunSummary, ...]:
        identity = _canonical_identity(batch_identity)
        _validate_page(limit, before_run_id, "before_run_id")
        self._require_formal_batch(identity)
        params = (identity, before_run_id, before_run_id, limit)
        rows = self._fetch_reprocess_runs(params)
        return tuple(_reprocess_run(row) for row in rows)

    def _require_formal_batch(self, batch_identity: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 AS batch_exists
                FROM finance_import_batch_contracts
                WHERE batch_identity=%s
                LIMIT 1
                """,
                (batch_identity,),
            )
            row = cursor.fetchone()
        if row is None:
            raise FinanceImportQueryNotFound("finance import batch was not found")

    def _fetch_manifest(self, batch_identity: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT batch.id AS batch_id, contract.batch_identity,
                       batch.format_id, batch.source_file, batch.sheet_name,
                       batch.header_row, batch.row_count AS source_row_count,
                       batch.status, contract.batch_version,
                       contract.source_content_digest,
                       contract.classifier_version,
                       contract.fingerprint_version,
                       batch.created_at, batch.completed_at,
                       (SELECT COUNT(DISTINCT occurrence.finance_import_row_id)
                          FROM finance_import_occurrences occurrence
                         WHERE occurrence.batch_id=batch.id)
                           AS canonical_row_count,
                       (SELECT COUNT(*)
                          FROM finance_import_occurrences occurrence
                         WHERE occurrence.batch_id=batch.id)
                           AS occurrence_count,
                       (SELECT COUNT(*)
                          FROM finance_import_classification_events event
                         WHERE event.batch_id=batch.id
                           AND event.disposition IN (
                               'manual_review','business_pending','blocked'
                           )
                           AND event.classification_version=(
                               SELECT MAX(latest.classification_version)
                                 FROM finance_import_classification_events latest
                                WHERE latest.batch_id=batch.id
                                  AND latest.finance_import_row_id=
                                      event.finance_import_row_id
                           )) AS review_count,
                       (SELECT COUNT(*)
                          FROM finance_import_dispatch_events dispatch
                         WHERE dispatch.batch_id=batch.id)
                           AS dispatch_event_count,
                       (SELECT COUNT(DISTINCT receipt.id)
                          FROM finance_import_reconciliation_receipts receipt
                          JOIN finance_import_occurrences occurrence
                            ON occurrence.finance_import_row_id=
                               receipt.finance_import_row_id
                         WHERE occurrence.batch_id=batch.id)
                           AS reconciliation_receipt_count
                FROM finance_import_batches batch
                JOIN finance_import_batch_contracts contract
                  ON contract.batch_id=batch.id
                WHERE contract.batch_identity=%s
                """,
                (batch_identity,),
            )
            return cursor.fetchone()

    def _fetch_review_rows(self, params: tuple[Any, ...]):
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT finance_row.id AS row_id, finance_row.transaction_date, finance_row.direction,
                       finance_row.debit, finance_row.credit, finance_row.reconciliation_status,
                       finance_row.created_at, event.classification_type,
                       event.disposition, event.available_actions,
                       (SELECT occurrence.sheet_name
                          FROM finance_import_occurrences occurrence
                         WHERE occurrence.batch_id=contract.batch_id
                           AND occurrence.finance_import_row_id=finance_row.id
                         ORDER BY occurrence.id DESC LIMIT 1) AS source_sheet,
                       (SELECT occurrence.source_row
                          FROM finance_import_occurrences occurrence
                         WHERE occurrence.batch_id=contract.batch_id
                           AND occurrence.finance_import_row_id=finance_row.id
                         ORDER BY occurrence.id DESC LIMIT 1) AS source_row,
                       (SELECT COUNT(*)
                          FROM finance_import_occurrences occurrence
                         WHERE occurrence.batch_id=contract.batch_id
                           AND occurrence.finance_import_row_id=finance_row.id)
                           AS occurrence_count
                FROM finance_import_batch_contracts contract
                JOIN finance_import_rows finance_row
                  ON EXISTS (
                      SELECT 1 FROM finance_import_occurrences occurrence
                       WHERE occurrence.batch_id=contract.batch_id
                         AND occurrence.finance_import_row_id=finance_row.id
                  )
                JOIN finance_import_classification_events event
                  ON event.id=(
                      SELECT latest.id
                        FROM finance_import_classification_events latest
                         WHERE latest.batch_id=contract.batch_id
                           AND latest.finance_import_row_id=finance_row.id
                       ORDER BY latest.classification_version DESC,
                                latest.id DESC
                       LIMIT 1
                  )
                WHERE contract.batch_identity=%s
                  AND (%s IS NULL OR finance_row.id>%s)
                  AND event.disposition IN (%s,%s,%s)
                ORDER BY finance_row.id ASC
                LIMIT %s
                """,
                params,
            )
            return tuple(cursor.fetchall())

    def _fetch_reprocess_runs(self, params: tuple[Any, ...]):
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT run.id AS run_id, contract.batch_identity,
                       run.classifier_version, run.plan_fingerprint,
                       run.selected_count, run.changed_count,
                       run.dispatch_count, run.reconciled_count,
                       run.pending_count, run.status,
                       run.created_at, run.completed_at
                FROM finance_import_reprocess_runs run
                JOIN finance_import_batch_contracts contract
                  ON contract.batch_id=run.batch_id
                WHERE contract.batch_identity=%s
                  AND (%s IS NULL OR run.id<%s)
                ORDER BY run.id DESC
                LIMIT %s
                """,
                params,
            )
            return tuple(cursor.fetchall())


def _validate_page(limit: int, cursor: int | None, cursor_name: str) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an integer between 1 and 100")
    if not 1 <= limit <= _MAXIMUM_PAGE_SIZE:
        raise ValueError("limit must be an integer between 1 and 100")
    if cursor is None:
        return
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 1:
        raise ValueError(f"{cursor_name} must be a positive integer")


def _canonical_identity(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("batch_identity is required")
    return value.strip()


def _batch_summary(row: dict[str, Any]) -> FinanceImportBatchSummary:
    return FinanceImportBatchSummary(
        int(row["batch_id"]),
        row.get("batch_identity"),
        str(row["format_id"]),
        _source_filename(row.get("source_file")),
        int(row["row_count"]),
        str(row["status"]),
        _optional_integer(row.get("batch_version")),
        row.get("batch_identity") is not None,
        row["created_at"],
    )


def _batch_manifest(row: dict[str, Any]) -> FinanceImportBatchManifest:
    return FinanceImportBatchManifest(
        int(row["batch_id"]), str(row["batch_identity"]), str(row["format_id"]),
        _source_filename(row.get("source_file")), str(row["sheet_name"]),
        int(row["header_row"]), int(row["source_row_count"]), str(row["status"]),
        int(row["batch_version"]), str(row["source_content_digest"]),
        str(row["classifier_version"]), str(row["fingerprint_version"]),
        int(row["canonical_row_count"]), int(row["occurrence_count"]),
        int(row["review_count"]), int(row["dispatch_event_count"]),
        int(row["reconciliation_receipt_count"]), row["created_at"],
        row.get("completed_at"),
    )


def _review_row(row: dict[str, Any]) -> FinanceImportReviewRowSummary:
    row_id = int(row["row_id"])
    return FinanceImportReviewRowSummary(
        row_id, f"finance-import-row:{row_id}", row.get("transaction_date"),
        str(row["direction"]), _integer_money(row), str(row["classification_type"]),
        str(row["disposition"]), str(row["reconciliation_status"]),
        str(row["source_sheet"]), int(row["source_row"]), int(row["occurrence_count"]),
        _text_tuple(row.get("available_actions")), row["created_at"],
    )


def _reprocess_run(row: dict[str, Any]) -> FinanceImportReprocessRunSummary:
    return FinanceImportReprocessRunSummary(
        int(row["run_id"]), str(row["batch_identity"]),
        str(row["classifier_version"]), str(row["plan_fingerprint"]),
        int(row["selected_count"]), int(row["changed_count"]),
        int(row["dispatch_count"]), int(row["reconciled_count"]),
        int(row["pending_count"]), str(row["status"]), row["created_at"],
        row["completed_at"],
    )


def _batch_apply_receipt(row: dict[str, Any]) -> FinanceImportBatchApplyReceipt:
    snapshot = row.get("result_snapshot")
    parsed = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    if not isinstance(parsed, dict) or set(parsed) != {
        "batch_identity", "resulting_batch_version", "preview_fingerprint",
        "reconciled_count", "existing_count", "pending_count",
    }:
        raise ValueError("finance_import_apply_receipt_contract_invalid")
    batch_identity = parsed["batch_identity"]
    fingerprint = parsed["preview_fingerprint"]
    numbers = tuple(parsed[key] for key in ("resulting_batch_version", "reconciled_count", "existing_count", "pending_count"))
    if not isinstance(batch_identity, str) or not batch_identity.strip() or not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(not isinstance(value, int) or isinstance(value, bool) for value in numbers):
        raise ValueError("finance_import_apply_receipt_contract_invalid")
    if numbers[0] < 1 or any(value < 0 for value in numbers[1:]):
        raise ValueError("finance_import_apply_receipt_contract_invalid")
    return FinanceImportBatchApplyReceipt(batch_identity, numbers[0], fingerprint, numbers[1], numbers[2], numbers[3])


def _correction_apply_receipt(
    row: dict[str, Any],
) -> FinanceImportCorrectionApplyReceipt:
    snapshot = row.get("result_snapshot")
    parsed = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    required = {
        "row_identity", "batch_identity", "resulting_batch_version",
        "classification_event_count", "ledger_entry_count", "allocation_count",
        "reconciliation_receipt_count", "alert_resolved_event_count",
        "preview_fingerprint",
    }
    if not isinstance(parsed, dict) or set(parsed) != required:
        raise ValueError("finance_import_correction_receipt_contract_invalid")
    identities = (parsed["row_identity"], parsed["batch_identity"])
    fingerprint = parsed["preview_fingerprint"]
    number_keys = (
        "resulting_batch_version", "classification_event_count", "ledger_entry_count",
        "allocation_count", "reconciliation_receipt_count", "alert_resolved_event_count",
    )
    numbers = tuple(parsed[key] for key in number_keys)
    if (
        any(not isinstance(value, str) or not value.strip() for value in identities)
        or not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(not isinstance(value, int) or isinstance(value, bool) for value in numbers)
        or any(value < 1 for value in numbers)
    ):
        raise ValueError("finance_import_correction_receipt_contract_invalid")
    return FinanceImportCorrectionApplyReceipt(*identities, *numbers, fingerprint)


def _integer_money(row: dict[str, Any]) -> int:
    debit = Decimal(str(row.get("debit") or 0))
    credit = Decimal(str(row.get("credit") or 0))
    amount = credit if credit > 0 else debit
    if amount <= 0 or amount != amount.to_integral_value():
        raise ValueError("finance import review amount must be positive integer NTD")
    return int(amount)


def _text_tuple(value: Any) -> tuple[str, ...]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("available_actions must be a JSON array")
    return tuple(str(item) for item in parsed)


def _source_filename(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).replace("\\", "/").rsplit("/", 1)[-1]


def _optional_integer(value: Any) -> int | None:
    return None if value is None else int(value)
