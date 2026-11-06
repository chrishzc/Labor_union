"""
File: query.py
Description: 讀取 Finance Import batch、review、reprocess 與已遮罩的 terminal receipt projection。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
from typing import Any
from domains.finance_import.cancellation_code import (
    extract_sinopac_memo_case_suffix,
    sinopac_memo_case_suffixes,
    resolve_finance_cancellation_code,
)
from domains.finance_import.statement_archive import bank_import_type
from domains.finance_import.ingestion import FinanceWorkbookIngestionReceipt
from domains.finance_import.transaction_classifier import _is_same_month
from subsystems.client_finance.virtual_account_resolution import (
    resolve_client_virtual_account,
    resolve_client_virtual_account_suffix,
)


_MAXIMUM_PAGE_SIZE = 100
_REVIEW_DISPOSITIONS = ("manual_review", "business_pending", "blocked", "create")
# A reimport links to the original bank fact and its latest classification.
_REVIEW_ROW_JOINS = """
JOIN finance_import_rows finance_row
  ON EXISTS (
      SELECT 1 FROM finance_import_occurrences occurrence
       WHERE occurrence.batch_id=contract.batch_id
         AND occurrence.finance_import_row_id=finance_row.id
  )
JOIN finance_import_classification_events event
  ON event.id=(
      SELECT MAX(latest.id) FROM finance_import_classification_events latest
       WHERE latest.finance_import_row_id=finance_row.id
  )
"""
# Every unresolved canonical bank fact is visible, including unmatched and
# blocked rows. Formal owner postings take precedence over stale classifications.
_REVIEW_ROW_PREDICATE = """
NOT EXISTS (
    SELECT 1 FROM client_ledger_entries posted_client
    WHERE posted_client.finance_import_row_id=finance_row.id
)
AND NOT EXISTS (
    SELECT 1 FROM staff_payout_events posted_payout
    WHERE posted_payout.finance_import_row_id=finance_row.id
)
AND NOT EXISTS (
    SELECT 1 FROM finance_import_reconciliation_receipts posted_receipt
    WHERE posted_receipt.finance_import_row_id=finance_row.id
)
AND NOT EXISTS (
    SELECT 1 FROM government_subsidy_period_entries posted_period
    WHERE posted_period.finance_import_row_id=finance_row.id
)
AND NOT EXISTS (
    SELECT 1 FROM finance_import_dispatch_events posted_dispatch
    WHERE posted_dispatch.finance_import_row_id=finance_row.id
      AND posted_dispatch.outcome IN ('reconciled','existing')
)
"""


BANK_CASE_PROOFS_SQL = """
SELECT finance_import_row_id AS row_id,case_no FROM client_ledger_entries WHERE finance_import_row_id IS NOT NULL
UNION
SELECT e.finance_import_row_id,o.case_no FROM staff_payout_events e
JOIN staff_payout_obligation_links l ON l.payout_event_id=e.id
JOIN staff_obligations o ON o.obligation_identity=l.obligation_identity WHERE e.finance_import_row_id IS NOT NULL
UNION
SELECT t.finance_import_row_id,i.case_no FROM government_subsidy_transactions t
JOIN government_subsidy_allocations a ON a.transaction_id=t.id
JOIN subsidy_claim_batch_items i ON i.id=a.claim_item_id
WHERE t.finance_import_row_id IS NOT NULL AND t.transaction_status='succeeded'
UNION
SELECT entry.finance_import_row_id,member.case_no FROM government_subsidy_period_entries entry
JOIN government_subsidy_period_members member ON member.receipt_id=COALESCE(entry.reversal_of_id,entry.id)
UNION
SELECT event.finance_import_row_id,o.case_no FROM staff_overpayment_recovery_events event
JOIN staff_overpayment_recoveries recovery ON recovery.recovery_identity=event.recovery_identity
JOIN staff_obligations o ON JSON_CONTAINS(recovery.source_obligation_identities,JSON_QUOTE(o.obligation_identity))
WHERE event.event_type='cash_recovered' AND event.finance_import_row_id IS NOT NULL
"""

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
    bank_type: str = "legacy"


@dataclass(frozen=True, slots=True)
class FinanceImportSourceReviewSummary:
    review_id: int
    review_identity: str
    source_sheet: str
    source_row: int
    issue_codes: tuple[str, ...]
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

    def bank_transactions(
        self, *, bank, direction, status, start, end, search, limit, before_row_id,
    ):
        _validate_page(limit, before_row_id, "before_row_id")
        if start and end and start > end:
            raise ValueError("bank_transaction_invalid_date_range")
        search = search.strip()
        conditions, params = [], []
        if bank:
            conditions.append("finance_row.format_id IN ('sinopac','legacy')" if bank == "sinopac"
                              else "finance_row.format_id='taishin'")
        for value, condition in (
            (direction, "finance_row.direction=%s"),
            (start, "finance_row.transaction_date>=%s"),
            (end, "finance_row.transaction_date<=%s"),
        ):
            if value:
                conditions.append(condition)
                params.append(value)
        where = " AND ".join(conditions) if conditions else "1=1"
        scoped = f"""
            WITH proofs AS ({BANK_CASE_PROOFS_SQL}),
            raw_rows AS (
                SELECT finance_row.id AS row_id, finance_row.transaction_date, finance_row.format_id,
                    finance_row.direction, finance_row.debit, finance_row.credit,
                    finance_row.sheet_name, finance_row.source_row,
                    finance_row.counterparty_name,
                    finance_row.cancellation_code, finance_row.bank_references,
                    finance_row.memo, finance_row.matched_identity_ids,
                    (JSON_UNQUOTE(JSON_EXTRACT(finance_row.bank_references,'$.source'))='manual_supplement') AS is_manual_supplement,
                    CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(finance_row.bank_references,'$.source'))='manual_supplement'
                        THEN '人工補登'
                        ELSE COALESCE(finance_row.source_reference, NULLIF(JSON_UNQUOTE(JSON_EXTRACT(
                        finance_row.bank_references, CASE finance_row.format_id
                            WHEN 'taishin' THEN '$.sequence'
                            WHEN 'legacy' THEN '$.transaction_reference'
                            ELSE '$."交易參考編號"' END
                    )), 'null')) END AS raw_reference,
                    COALESCE(event.classification_type,finance_row.classification_type) classification_type,
                    event.reason AS event_reason,
                    COALESCE(finance_row.classification_reason,event.reason) AS review_reason,
                    COALESCE(event.target_identities,JSON_ARRAY()) AS target_identities,
                    COALESCE(event.available_actions,JSON_ARRAY()) AS available_actions,
                    CASE WHEN EXISTS (
                        SELECT 1 FROM finance_import_integrity_events issue
                        WHERE issue.finance_import_row_id=finance_row.id AND issue.active=1
                          AND issue.id=(SELECT MAX(latest.id) FROM finance_import_integrity_events latest
                            WHERE latest.finance_import_row_id=issue.finance_import_row_id
                              AND latest.batch_id=issue.batch_id AND latest.issue_code=issue.issue_code)
                    ) THEN 'blocked' ELSE COALESCE(event.disposition,'manual_review') END disposition,
                    CASE WHEN ({_REVIEW_ROW_PREDICATE})
                        AND NOT EXISTS (SELECT 1 FROM proofs WHERE row_id=finance_row.id)
                        THEN 'pending' ELSE 'posted' END AS transaction_status
                FROM finance_import_rows finance_row
                LEFT JOIN finance_import_classification_events event ON event.id=(
                    SELECT MAX(latest.id) FROM finance_import_classification_events latest
                    WHERE latest.finance_import_row_id=finance_row.id
                )
                WHERE {where}
            ),
            bank_rows AS (
                SELECT raw_rows.*, CASE
                    WHEN raw_reference REGEXP '[0-9][0-9 -]{6,}[0-9]'
                        THEN CONCAT('****',RIGHT(raw_reference,4))
                    ELSE raw_reference END AS safe_reference
                FROM raw_rows
                WHERE transaction_status='posted'
                   OR is_manual_supplement=1
                   OR (
                       COALESCE(classification_type,'')<>'non_business_review'
                       AND NOT (
                           format_id='taishin'
                           AND direction='incoming'
                           AND classification_type='government_subsidy'
                           AND COALESCE(event_reason,'initial_bank_classification')='initial_bank_classification'
                           AND LOCATE('新竹市政府',COALESCE(memo,''))=0
                           AND LOCATE('新竹市府',COALESCE(memo,''))=0
                       )
                       AND NOT (
                           classification_type IN ('staff_payout','staff_salary','staff_legacy_subsidy','client_refund','client_subsidy_return')
                           AND COALESCE(event_reason,'initial_bank_classification')='initial_bank_classification'
                           AND JSON_LENGTH(COALESCE(matched_identity_ids,JSON_ARRAY()))=0
                           AND JSON_LENGTH(COALESCE(target_identities,JSON_ARRAY()))=0
                           AND COALESCE(memo,'') NOT REGEXP '[0-9]{{6}}'
                       )
                   )
            )
        """
        if search:
            scoped += """,
                matched AS (
                    SELECT bank_rows.* FROM bank_rows
                    WHERE LOCATE(%s,CONCAT_WS(' ',CONCAT('bank:',row_id),
                        CONCAT(sheet_name,'#',source_row), safe_reference, counterparty_name,
                        cancellation_code, memo,
                        CASE WHEN classification_type='government_subsidy' THEN '新竹市政府' ELSE '' END))>0
                      OR EXISTS (SELECT 1 FROM proofs
                           WHERE proofs.row_id=bank_rows.row_id AND LOCATE(%s,proofs.case_no)>0)
                      OR (bank_rows.classification_type IN ('staff_payout','staff_salary','staff_legacy_subsidy')
                          AND EXISTS (SELECT 1 FROM staff s
                               WHERE JSON_CONTAINS(COALESCE(bank_rows.matched_identity_ids,JSON_ARRAY()),CAST(s.id AS JSON))
                                 AND LOCATE(%s,s.name)>0))
                      OR (bank_rows.classification_type IN ('client_receipt','client_refund','client_subsidy_return')
                          AND EXISTS (SELECT 1 FROM clients c
                               WHERE JSON_CONTAINS(COALESCE(bank_rows.matched_identity_ids,JSON_ARRAY()),CAST(c.id AS JSON))
                                 AND LOCATE(%s,c.name)>0))
                )
            """
            params.extend((search, search, search, search))
        scope = "matched" if search else "bank_rows"
        with self._connection.cursor() as cursor:
            pending_count = None
            if status != "posted":
                cursor.execute(scoped + f"SELECT COUNT(*) AS total FROM {scope} WHERE transaction_status='pending'", params)
                pending_count = int(cursor.fetchone()["total"])
            predicates, page_params = [], list(params)
            if status != "all":
                predicates.append("transaction_status=%s")
                page_params.append(status)
            if before_row_id is not None:
                predicates.append("row_id<%s")
                page_params.append(before_row_id)
            page_where = " AND ".join(predicates) if predicates else "1=1"
            cursor.execute(scoped + f"SELECT * FROM {scope} WHERE {page_where} ORDER BY row_id DESC LIMIT %s",
                           (*page_params, limit + 1))
            rows = cursor.fetchall()
            page = rows[:limit]
            cases_by_id = {}
            if page:
                ids = tuple(row["row_id"] for row in page)
                placeholders = ",".join("%s" for _ in ids)
                cursor.execute(
                    f"SELECT row_id,case_no FROM ({BANK_CASE_PROOFS_SQL}) proofs "
                    f"WHERE row_id IN ({placeholders}) ORDER BY row_id,case_no", ids,
                )
                for case in cursor.fetchall():
                    cases_by_id.setdefault(case["row_id"], []).append(case["case_no"])
            items = _enrich_bank_transactions(cursor, page, cases_by_id)
        return {
            "items": items,
            "pending_count": pending_count,
            "next_before_row_id": int(page[-1]["row_id"]) if len(rows) > limit else None,
        }

    def import_history(self, *, limit, before):
        kind, record_id = None, None
        if before is not None:
            kind, _, raw_id = before.partition(":")
            if kind not in {"attempt", "batch"} or not raw_id.isascii() or not raw_id.isdecimal():
                raise ValueError("invalid_import_history_cursor")
            record_id = int(raw_id)
        _validate_page(limit, record_id, "before_history_id")
        segment = 1 if kind == "attempt" else 0 if kind == "batch" else None
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                WITH uploads AS (
                    SELECT 1 AS segment, attempt.id,attempt.started_at,attempt.transaction_outcome,
                           attempt.error_code,attempt.batch_id,attempt.idempotency_key
                    FROM finance_import_ingestion_attempts attempt
                    UNION ALL
                    SELECT 0,prior.id,prior.created_at,'legacy',NULL,prior.id,NULL
                    FROM finance_import_batches prior
                    WHERE NOT EXISTS (SELECT 1 FROM finance_import_ingestion_attempts
                                      WHERE batch_id=prior.id)
                ),
                page AS (
                    SELECT * FROM uploads
                    WHERE (%s IS NULL OR segment<%s OR (segment=%s AND id<%s))
                    ORDER BY segment DESC,id DESC LIMIT %s
                )
                SELECT page.*,batch.format_id,batch.source_file,
                    saved.result_snapshot AS ingestion_snapshot, applied.result_snapshot AS apply_snapshot,
                    job.status AS apply_job_status
                FROM page
                LEFT JOIN finance_import_batches batch ON batch.id=page.batch_id
                LEFT JOIN finance_import_batch_contracts contract ON contract.batch_id=batch.id
                LEFT JOIN finance_import_ingestion_receipts saved ON saved.idempotency_key=page.idempotency_key
                LEFT JOIN finance_import_apply_receipts applied ON applied.id=(
                    SELECT MIN(receipt.id) FROM finance_import_apply_receipts receipt WHERE receipt.batch_id=batch.id
                )
                LEFT JOIN background_jobs job ON job.command_identity=(
                    SELECT latest.command_identity FROM background_jobs latest
                    WHERE latest.command_type='finance_import_batch_apply'
                      AND JSON_UNQUOTE(JSON_EXTRACT(latest.command_payload,'$.batch_identity'))=contract.batch_identity
                    ORDER BY latest.created_at DESC,latest.job_id DESC LIMIT 1
                )
                ORDER BY page.segment DESC,page.id DESC
                """, (segment, segment, segment, record_id, limit + 1),
            )
            rows = cursor.fetchall()
        page = [_import_history_entry(row) for row in rows[:limit]]
        return {"items": page, "next_before": page[-1]["identity"] if len(rows) > limit else None}

    def ingestion_outcome(self, key: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT attempt.transaction_outcome,attempt.error_code,attempt.phase,
                          attempt.source_content_digest,saved.result_snapshot
                   FROM finance_import_ingestion_attempts attempt
                   LEFT JOIN finance_import_ingestion_receipts saved ON saved.idempotency_key=attempt.idempotency_key
                   WHERE attempt.idempotency_key=%s""", (key,),
            )
            row = cursor.fetchone()
        if row is None:
            return {"status": "unknown", "receipt": None, "source_content_digest": None, "error_code": None, "phase": None}
        receipt = _history_snapshot(row["result_snapshot"])
        receipt.pop("history", None)
        return {
            "status": row["transaction_outcome"],
            "receipt": FinanceWorkbookIngestionReceipt(**receipt) if receipt else None,
            "source_content_digest": row["source_content_digest"],
            "error_code": row["error_code"],
            "phase": row["phase"],
        }

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

    def list_source_reviews(
        self, batch_identity: str, *, limit: int,
        after_source_review_id: int | None = None,
    ) -> tuple[FinanceImportSourceReviewSummary, ...]:
        identity = _canonical_identity(batch_identity)
        _validate_page(limit, after_source_review_id, "after_source_review_id")
        self._require_formal_batch(identity)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT review.id AS review_id, review.review_identity,
                       review.sheet_name AS source_sheet, review.source_row,
                       review.issue_codes, review.created_at
                FROM finance_import_batch_contracts contract
                JOIN finance_import_source_review_occurrences occurrence
                  ON occurrence.batch_id=contract.batch_id
                JOIN finance_import_source_reviews review
                  ON review.id=occurrence.review_id
                WHERE contract.batch_identity=%s
                  AND (%s IS NULL OR review.id>%s)
                ORDER BY review.id ASC LIMIT %s
                """,
                (identity, after_source_review_id, after_source_review_id, limit),
            )
            rows = tuple(cursor.fetchall())
        return tuple(FinanceImportSourceReviewSummary(
            int(row["review_id"]), str(row["review_identity"]),
            str(row["source_sheet"]), int(row["source_row"]),
            _text_tuple(row["issue_codes"]), row["created_at"],
        ) for row in rows)

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
                f"""
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
                           FROM finance_import_batch_contracts contract
                           {_REVIEW_ROW_JOINS}
                          WHERE contract.batch_id=batch.id
                            AND event.disposition IN (
                               'manual_review','business_pending','blocked','create'
                           )
                            AND {_REVIEW_ROW_PREDICATE}) AS review_count,
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
                f"""
                SELECT finance_row.id AS row_id, finance_row.transaction_date, finance_row.direction, finance_row.format_id,
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
                 {_REVIEW_ROW_JOINS}
                WHERE contract.batch_identity=%s
                  AND (%s IS NULL OR finance_row.id>%s)
                  AND event.disposition IN (%s,%s,%s,%s)
                  AND {_REVIEW_ROW_PREDICATE}
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
    classification_type = str(row.get("classification_type") or "")
    direction = str(row.get("direction") or "")
    format_id = str(row.get("format_id", "legacy"))

    if classification_type in ("staff_payout", "staff_salary", "staff_legacy_subsidy"):
        b_type = "payable"
    elif classification_type == "client_receipt":
        b_type = "receivable"
    elif classification_type == "government_subsidy":
        b_type = "government_subsidy"
    elif classification_type in ("client_refund", "client_subsidy_return"):
        b_type = "subsidy_return"
    elif classification_type == "non_business_review":
        b_type = "review"
    else:
        b_type = bank_import_type(format_id, direction)

    return FinanceImportReviewRowSummary(
        row_id, f"finance-import-row:{row_id}", row.get("transaction_date"),
        direction, _integer_money(row), classification_type,
        str(row["disposition"]), str(row["reconciliation_status"]),
        str(row["source_sheet"]), int(row["source_row"]), int(row["occurrence_count"]),
        _text_tuple(row.get("available_actions")), row["created_at"],
        b_type,
    )


def _json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _json_list(raw: Any) -> list[Any]:
    if isinstance(raw, (list, tuple)):
        return list(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _single_entity_id(row: Mapping[str, Any], prefix: str) -> int | None:
    targets = [
        str(item)
        for item in _json_list(row.get("target_identities"))
        if isinstance(item, str) and item.startswith(prefix)
    ]
    if len(targets) == 1:
        raw_val = targets[0].removeprefix(prefix)
        if raw_val.isdigit() and int(raw_val) > 0:
            return int(raw_val)
    matched = [
        int(item)
        for item in _json_list(row.get("matched_identity_ids"))
        if isinstance(item, int) and not isinstance(item, bool) and item > 0
    ]
    unique_matched = sorted(set(matched))
    return unique_matched[0] if len(unique_matched) == 1 else None


def _enrich_bank_transactions(
    cursor: Any,
    page: Sequence[Mapping[str, Any]],
    posted_cases_by_id: Mapping[int, list[str]],
) -> list[dict[str, Any]]:
    if not page:
        return []
    client_name_cache: dict[int, str | None] = {}
    staff_name_cache: dict[int, str | None] = {}
    case_client_name_cache: dict[str, str | None] = {}
    case_staff_name_cache: dict[str, str | None] = {}
    va_cache: dict[str, str | None] = {}
    suffix_cache: dict[str, str | None] = {}
    receipt_obligations: dict[str, Sequence[Mapping[str, Any]]] = {}

    def client_name_by_id(client_id: int) -> str | None:
        if client_id not in client_name_cache:
            cursor.execute("SELECT name FROM clients WHERE id=%s", (client_id,))
            found = cursor.fetchone()
            client_name_cache[client_id] = str(found["name"]).strip() if found and found.get("name") else None
        return client_name_cache[client_id]

    def staff_name_by_id(staff_id: int) -> str | None:
        if staff_id not in staff_name_cache:
            cursor.execute("SELECT name FROM staff WHERE id=%s", (staff_id,))
            found = cursor.fetchone()
            staff_name_cache[staff_id] = str(found["name"]).strip() if found and found.get("name") else None
        return staff_name_cache[staff_id]

    def client_name_by_case(case_no: str) -> str | None:
        if case_no not in case_client_name_cache:
            cursor.execute(
                "SELECT c.name FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s",
                (case_no,),
            )
            found = cursor.fetchone()
            case_client_name_cache[case_no] = str(found["name"]).strip() if found and found.get("name") else None
        return case_client_name_cache[case_no]

    def staff_name_by_case(case_no: str) -> str | None:
        if case_no not in case_staff_name_cache:
            cursor.execute(
                "SELECT s.name FROM orders o JOIN staff s ON s.id=o.staff_id WHERE o.case_no=%s",
                (case_no,),
            )
            found = cursor.fetchone()
            if not (found and found.get("name")):
                cursor.execute(
                    "SELECT DISTINCT s.name FROM staff_obligations o "
                    "JOIN staff s ON s.id=o.staff_id "
                    "WHERE o.case_no=%s AND o.status<>'cancelled'",
                    (case_no,),
                )
                names = [str(r["name"]).strip() for r in cursor.fetchall() if r.get("name")]
                case_staff_name_cache[case_no] = names[0] if len(set(names)) == 1 else None
            else:
                case_staff_name_cache[case_no] = str(found["name"]).strip()
        return case_staff_name_cache[case_no]

    def resolve_va(code: str) -> str | None:
        if code not in va_cache:
            res = resolve_client_virtual_account(cursor, code)
            va_cache[code] = str(res["case_no"]) if res["result"] == "resolved" and res["case_no"] else None
        return va_cache[code]

    def resolve_suffix(suffix: str | None) -> str | None:
        if suffix is None:
            return None
        if suffix not in suffix_cache:
            res = resolve_client_virtual_account_suffix(cursor, suffix)
            suffix_cache[suffix] = str(res["case_no"]) if res["result"] == "resolved" and res["case_no"] else None
        return suffix_cache[suffix]

    enriched = []
    for row in page:
        row_id = int(row["row_id"])
        c_type = str(row.get("classification_type") or "")
        status = str(row.get("transaction_status") or "pending")
        review_reason = row["review_reason"]
        target = None
        target_rows = ()
        target_staff_id = None
        cases = list(dict.fromkeys(posted_cases_by_id.get(row_id, [])))
        cp_name = str(row["counterparty_name"]).strip() if row.get("counterparty_name") else None

        if c_type == "government_subsidy":
            cp_name = cp_name or "新竹市政府"
        elif c_type == "client_receipt":
            client_id = _single_entity_id(row, "client:")
            if status == "pending" and not cases:
                code = resolve_finance_cancellation_code(
                    {
                        "format_id": row.get("format_id"),
                        "cancellation_code": row.get("cancellation_code"),
                        "bank_references": _json_dict(row.get("bank_references")),
                    }
                )["cancellation_code"]
                if code:
                    resolved_case = resolve_va(code)
                    if resolved_case:
                        cases = [resolved_case]
                        if resolved_case not in receipt_obligations:
                            cursor.execute(
                                "SELECT obligation_identity, due_date, amount_due_ntd FROM client_obligations "
                                "WHERE case_no=%s AND direction='receivable_from_client' "
                                "AND status='open' AND amount_due_ntd>0",
                                (resolved_case,),
                            )
                            receipt_obligations[resolved_case] = cursor.fetchall()
                        open_rows = receipt_obligations[resolved_case]
                        target_rows = open_rows
                        bank_amount = _integer_money(row)
                        if not any(int(item["amount_due_ntd"]) == bank_amount for item in open_rows):
                            month_rows = [
                                item for item in open_rows
                                if _is_same_month(row.get("transaction_date"), item.get("due_date"))
                            ]
                            if len(month_rows) == 1:
                                review_reason = (
                                    "sinopac_client_receipt_shortfall"
                                    if bank_amount < int(month_rows[0]["amount_due_ntd"])
                                    else "sinopac_client_receipt_overage"
                                )
                elif client_id is not None:
                    cursor.execute(
                        "SELECT o.case_no, o.due_date, o.obligation_identity, o.amount_due_ntd FROM client_obligations o "
                        "JOIN orders ord ON ord.case_no=o.case_no "
                        "WHERE ord.client_id=%s AND o.direction='receivable_from_client' AND o.status='open'",
                        (client_id,),
                    )
                    open_rows = cursor.fetchall()
                    target_rows = open_rows
                    month_cases = {
                        str(r["case_no"])
                        for r in open_rows
                        if r.get("case_no") and _is_same_month(row.get("transaction_date"), r.get("due_date"))
                    }
                    all_open_cases = {str(r["case_no"]) for r in open_rows if r.get("case_no")}
                    if len(month_cases) == 1:
                        cases = [next(iter(month_cases))]
                    elif len(all_open_cases) == 1:
                        cases = [next(iter(all_open_cases))]
                    else:
                        cursor.execute(
                            "SELECT DISTINCT case_no FROM orders WHERE client_id=%s AND status<>'訂單取消'",
                            (client_id,),
                        )
                        order_cases = {str(r["case_no"]) for r in cursor.fetchall() if r.get("case_no")}
                        if len(order_cases) == 1:
                            cases = [next(iter(order_cases))]
            if not cp_name:
                if cases:
                    cp_name = client_name_by_case(cases[0])
                if not cp_name and client_id is not None:
                    cp_name = client_name_by_id(client_id)
        elif c_type in {"staff_payout", "staff_salary", "staff_legacy_subsidy"}:
            staff_id = _single_entity_id(row, "staff:")
            if status == "pending" and not cases:
                suffix = extract_sinopac_memo_case_suffix(row.get("memo"))
                if suffix:
                    resolved_case = resolve_suffix(suffix)
                    if resolved_case:
                        cases = [resolved_case]
                if staff_id is not None:
                    cursor.execute(
                        "SELECT o.case_no, o.due_date, o.obligation_identity, "
                        "COALESCE(p.balance_ntd,o.amount_due_ntd) AS amount_due_ntd FROM staff_obligations o "
                        "LEFT JOIN staff_payable_projections p ON p.obligation_identity=o.obligation_identity "
                        "WHERE o.staff_id=%s AND o.direction='payable_to_staff' "
                        "AND o.status<>'cancelled' AND o.amount_due_ntd>0 "
                        "AND (p.status IS NULL OR p.status IN ('payable','partially_paid'))",
                        (staff_id,),
                    )
                    open_rows = cursor.fetchall()
                    target_rows = open_rows
                    target_staff_id = staff_id
                    month_cases = {
                        str(r["case_no"])
                        for r in open_rows
                        if r.get("case_no") and _is_same_month(row.get("transaction_date"), r.get("due_date"))
                    }
                    all_open_cases = {str(r["case_no"]) for r in open_rows if r.get("case_no")}
                    if not cases and len(month_cases) == 1:
                        cases = [next(iter(month_cases))]
                    elif not cases and len(all_open_cases) == 1:
                        cases = [next(iter(all_open_cases))]
                    elif not cases:
                        cursor.execute(
                            "SELECT DISTINCT case_no FROM orders WHERE staff_id=%s AND status<>'訂單取消'",
                            (staff_id,),
                        )
                        order_cases = {str(r["case_no"]) for r in cursor.fetchall() if r.get("case_no")}
                        if len(order_cases) == 1:
                            cases = [next(iter(order_cases))]
            if not cp_name:
                if staff_id is None and status == "posted":
                    cursor.execute(
                        "SELECT staff_id FROM staff_payout_events WHERE finance_import_row_id=%s LIMIT 1",
                        (row_id,),
                    )
                    posted_staff = cursor.fetchone()
                    if posted_staff and posted_staff.get("staff_id"):
                        staff_id = int(posted_staff["staff_id"])
                if staff_id is not None:
                    cp_name = staff_name_by_id(staff_id)
                if not cp_name and len(cases) == 1:
                    cp_name = staff_name_by_case(cases[0])
        elif c_type in {"client_refund", "client_subsidy_return", "client_refund_return"}:
            client_id = _single_entity_id(row, "client:")
            if status == "pending" and not cases:
                suffix = extract_sinopac_memo_case_suffix(row.get("memo"))
                if suffix:
                    resolved_case = resolve_suffix(suffix)
                    if resolved_case:
                        cases = [resolved_case]
                if client_id is not None:
                    type_sql = (
                        "AND o.obligation_type='subsidy_return'"
                        if c_type == "client_subsidy_return"
                        else "AND o.obligation_type IN ('refund','adjustment')"
                    )
                    cursor.execute(
                        "SELECT o.case_no, o.due_date, o.obligation_identity, o.amount_due_ntd FROM client_obligations o "
                        "JOIN orders ord ON ord.case_no=o.case_no "
                        f"WHERE ord.client_id=%s AND o.direction='payable_to_client' AND o.status='open' {type_sql}",
                        (client_id,),
                    )
                    open_rows = cursor.fetchall()
                    target_rows = open_rows if c_type != "client_refund_return" else ()
                    if not open_rows and not cases:
                        cursor.execute(
                            "SELECT DISTINCT o.case_no, o.due_date FROM client_obligations o "
                            "JOIN orders ord ON ord.case_no=o.case_no "
                            "WHERE ord.client_id=%s AND o.direction='payable_to_client' AND o.status='open'",
                            (client_id,),
                        )
                        open_rows = cursor.fetchall()
                    month_cases = {
                        str(r["case_no"])
                        for r in open_rows
                        if r.get("case_no") and _is_same_month(row.get("transaction_date"), r.get("due_date"))
                    }
                    all_open_cases = {str(r["case_no"]) for r in open_rows if r.get("case_no")}
                    if not cases and len(month_cases) == 1:
                        cases = [next(iter(month_cases))]
                    elif not cases and len(all_open_cases) == 1:
                        cases = [next(iter(all_open_cases))]
                    elif not cases:
                        cursor.execute(
                            "SELECT DISTINCT case_no FROM orders WHERE client_id=%s AND status<>'訂單取消'",
                            (client_id,),
                        )
                        order_cases = {str(r["case_no"]) for r in cursor.fetchall() if r.get("case_no")}
                        if len(order_cases) == 1:
                            cases = [next(iter(order_cases))]
            if not cp_name:
                if cases:
                    cp_name = client_name_by_case(cases[0])
                if not cp_name and client_id is not None:
                    cp_name = client_name_by_id(client_id)

        # This target opens the existing workflow. The owner revalidates it at Preview/Apply.
        if (
            status == "pending" and row["disposition"] != "blocked" and len(cases) == 1
            and (
                row["direction"] != "outgoing" or not sinopac_memo_case_suffixes(row.get("memo"))
                or resolve_suffix(extract_sinopac_memo_case_suffix(row.get("memo"))) == cases[0]
            )
        ):
            case_no = cases[0]
            scoped_rows = [
                item for item in target_rows
                if item.get("case_no", case_no) == case_no
                and item.get("obligation_identity") and int(item["amount_due_ntd"]) > 0
            ]
            month_rows = [
                item for item in scoped_rows
                if _is_same_month(row.get("transaction_date"), item.get("due_date"))
            ]
            amount = _integer_money(row)
            if c_type == "client_receipt":
                exact = [item for item in scoped_rows if int(item["amount_due_ntd"]) == amount]
                selected = exact if exact else month_rows
            elif len(month_rows) <= 1:
                selected = month_rows
            else:
                singles = [item for item in month_rows if 0 <= int(item["amount_due_ntd"]) - amount <= 100]
                grouped = 0 <= sum(int(item["amount_due_ntd"]) for item in month_rows) - amount <= 100
                selected = month_rows if grouped and not singles else singles if len(singles) == 1 and not grouped else []
            if selected and (c_type != "client_receipt" or len(selected) == 1):
                target = {
                    "case_no": case_no,
                    "obligation_identities": sorted(item["obligation_identity"] for item in selected),
                    "staff_id": target_staff_id,
                }

        enriched.append(_bank_transaction({**row, "counterparty_name": cp_name, "review_reason": review_reason}, cases, target))
    return enriched


def _bank_transaction(row, cases, reconciliation_target=None):
    bank = "taishin" if row["format_id"] == "taishin" else "sinopac"
    reference = row["safe_reference"]
    if not reference:
        reference = (
            f'{row["sheet_name"]}#{row["source_row"]}'
            if row["sheet_name"] and row["source_row"] else f'bank:{row["row_id"]}'
        )
    return {
        "row_id": int(row["row_id"]),
        "row_identity": f'finance-import-row:{row["row_id"]}',
        "transaction_date": row["transaction_date"],
        "bank": bank,
        "direction": row["direction"],
        "amount_ntd": _integer_money(row),
        "classification_type": row["classification_type"],
        "status": row["transaction_status"],
        "disposition": row["disposition"],
        "review_reason": row["review_reason"],
        "available_actions": _text_tuple(row["available_actions"]),
        "reference": reference,
        "counterparty_name": row["counterparty_name"],
        "cases": cases,
        "reconciliation_target": reconciliation_target,
    }


def batch_review_count(cursor, batch_id: int) -> int:
    """Capture the pending bank facts inside the receipt's own transaction."""
    cursor.execute(
        f"""SELECT COUNT(*) AS total FROM finance_import_batch_contracts contract
            {_REVIEW_ROW_JOINS}
            WHERE contract.batch_id=%s
              AND event.disposition IN ('manual_review','business_pending','blocked','create')
              AND {_REVIEW_ROW_PREDICATE}""",
        (batch_id,),
    )
    return int(cursor.fetchone()["total"])


def _history_snapshot(raw):
    return dict(json.loads(raw) if isinstance(raw, str) else raw or {})


def _import_history_entry(row):
    ingestion = _history_snapshot(row["ingestion_snapshot"])
    apply = _history_snapshot(row["apply_snapshot"])
    captured = (apply if apply else ingestion).get("history", {})
    job = row["apply_job_status"]
    if row["transaction_outcome"] == "rolled_back":
        status = "failed"
    elif apply:
        status = "posted"
    elif job in {"queued", "running"}:
        status = "posting"
    elif job in {"failed", "cancelled"}:
        status = "posting_failed"
    elif row["transaction_outcome"] == "legacy":
        status = "legacy"
    elif captured.get("blocked"):
        status = "blocked"
    else:
        status = "saved"
    bank = {"legacy": "sinopac", "sinopac": "sinopac", "taishin": "taishin"}.get(row["format_id"])
    return {
        "identity": f'{"attempt" if row["segment"] else "batch"}:{row["id"]}',
        "started_at": row["started_at"].isoformat() + "Z",
        "bank": bank,
        "source_file": _source_filename(row["source_file"]),
        "status": status,
        "new_count": ingestion.get("canonical_created_count"),
        "duplicate_count": ingestion.get("duplicate_occurrence_count"),
        "reconciled_count": apply.get("reconciled_count", 0) if status not in {"posting", "failed", "legacy"} else None,
        "pending_count": captured.get("pending_count") if status != "posting" else None,
        "source_warning_count": ingestion.get("source_warning_count"),
        "error_code": row["error_code"],
    }


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
    if isinstance(parsed, dict):
        parsed = {key: value for key, value in parsed.items() if key != "history"}
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
        or any(value < 1 for value in numbers[:-1])
        or numbers[-1] < 0
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
