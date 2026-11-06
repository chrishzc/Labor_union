"""
File: ingestion.py
Description: 將銀行工作簿安全入庫、保留初始分類與可辨識的冪等重播 receipt。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from domains.finance_import.ingestion import (
    FinanceImportAttempt,
    FinanceWorkbookIngestionReceipt,
    InitialClassificationFacts,
    build_initial_classification,
)
from domains.finance_import.source_warning_review import (
    build_finance_source_review,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, IdempotencyKey
from subsystems.finance_import.identity_maps import load_finance_identity_maps
from subsystems.finance_import.query import batch_review_count
from subsystems.finance_import.staging import (
    classify_row_with_identity_maps,
    stage_finance_rows,
)


_CLASSIFIER_VERSION = "finance-transaction-classifier-v5"
_FINGERPRINT_VERSION = "finance-transaction-fingerprint-v1"
_INITIAL_CLASSIFICATION_REASON = "initial_bank_classification"


@dataclass
class _IngestionProgress:
    phase: str = "normalization"


class FinanceImportAttemptError(RuntimeError):
    def __init__(self, attempt: FinanceImportAttempt) -> None:
        self.attempt = attempt
        super().__init__(attempt.error_code or "finance_import_ingestion_failed")


class _IdempotencyConflict(ValueError):
    def __init__(self) -> None:
        super().__init__("idempotency_conflict")


def ingest_finance_workbook(
    excel_path: str,
    idempotency_key: IdempotencyKey,
    actor: ActorContext,
    *,
    connection_factory: Callable[[], Any],
    normalizer: Callable[[str], Mapping[str, Any]],
    source_filename: str | None = None,
) -> FinanceWorkbookIngestionReceipt:
    # Kept cohesive: the primary UoW rollback and independent attempt audit are one boundary.
    source_path = _validated_source_path(excel_path)
    source_digest = _source_digest(source_path)
    command_fingerprint = _command_fingerprint(source_digest, actor)
    started_at = _utc_timestamp()
    progress = _IngestionProgress()
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            replay = _find_replay_or_attempt(cursor, idempotency_key, command_fingerprint)
        if replay is not None:
            return replay
        normalized_result = normalizer(str(source_path))
        if source_filename is not None:
            normalized_result = {
                **normalized_result, "source_file": source_filename,
                "normalized_rows": [
                    {**row, "source_file": source_filename}
                    for row in normalized_result["normalized_rows"]
                ],
            }
        receipt = _ingest_or_replay(
            connection,
            normalized_result,
            source_digest,
            command_fingerprint,
            idempotency_key,
            actor,
            progress,
        )
        with connection.cursor() as cursor:
            _save_success_attempt(
                cursor,
                idempotency_key,
                command_fingerprint,
                receipt,
                started_at,
            )
        connection.commit()
    except FinanceImportAttemptError:
        connection.rollback()
        raise
    except _IdempotencyConflict as error:
        connection.rollback()
        raise ValueError("idempotency_conflict") from error
    except Exception as error:
        connection.rollback()
        attempt = _record_failed_attempt(
            connection_factory,
            idempotency_key,
            command_fingerprint,
            source_digest,
            progress.phase,
            started_at,
            _attempt_error_code(error),
        )
        raise FinanceImportAttemptError(attempt) from error
    finally:
        connection.close()
    return receipt


def _filter_admitted_business_rows(
    normalized_result: Mapping[str, Any],
    identity_maps: Mapping[str, Any],
) -> dict[str, Any]:
    rows = normalized_result.get("normalized_rows")
    if not isinstance(rows, list):
        raise ValueError("normalized_rows must be a list")
    source_file = normalized_result.get("source_file")
    if source_file is None:
        source_files = {
            row.get("source_file")
            for row in rows
            if isinstance(row, Mapping) and row.get("source_file") is not None
        }
        if len(source_files) == 1:
            source_file = next(iter(source_files))
    admitted_rows = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each normalized row must be a mapping")
        classification = classify_row_with_identity_maps(row, identity_maps)
        if classification["classification_type"] == "non_business_review":
            continue
        admitted_rows.append(row)
    return {
        **normalized_result,
        **({"source_file": source_file} if source_file is not None else {}),
        "normalized_rows": admitted_rows,
        "source_row_count": len(admitted_rows),
    }


def _ingest_or_replay(
    connection: Any,
    normalized_result: Mapping[str, Any],
    source_digest: str,
    command_fingerprint: str,
    idempotency_key: IdempotencyKey,
    actor: ActorContext,
    progress: _IngestionProgress,
) -> FinanceWorkbookIngestionReceipt:
    with connection.cursor() as cursor:
        replay = _find_replay(cursor, idempotency_key, command_fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        progress.phase = "staging"
        identity_maps = load_finance_identity_maps(cursor)
        admitted_result = _filter_admitted_business_rows(
            normalized_result,
            identity_maps,
        )
        staged = stage_finance_rows(
            cursor,
            admitted_result,
            identity_maps,
        )
        _refresh_upgraded_existing_classifications(
            cursor,
            int(staged["batch_id"]),
            admitted_result["normalized_rows"],
            staged["staged_rows"],
            identity_maps,
            actor,
        )
        progress.phase = "classification"
        receipt = _persist_ingestion(
            cursor,
            staged,
            admitted_result,
            source_digest,
            actor,
        )
    progress.phase = "receipt"
    with connection.cursor() as cursor:
        _save_receipt(cursor, idempotency_key, command_fingerprint, receipt)
    return receipt


def _refresh_upgraded_existing_classifications(
    cursor: Any,
    batch_id: int,
    admitted_rows: list[Mapping[str, Any]],
    staged_rows: list[Mapping[str, Any]],
    identity_maps: Mapping[str, Any],
    actor: ActorContext,
) -> None:
    upgraded_ids: set[int] = set()
    for raw_row, staged_row in zip(admitted_rows, staged_rows):
        if staged_row.get("result") != "skipped_existing":
            continue
        row_id = int(staged_row["row_id"])
        if row_id in upgraded_ids:
            continue
        cursor.execute(
            "SELECT classification_version, canonical_fact_version, classification_type, reason "
            "FROM finance_import_classification_events "
            "WHERE finance_import_row_id=%s ORDER BY id DESC LIMIT 1",
            (row_id,),
        )
        latest = cursor.fetchone()
        if latest is None:
            continue
        latest_type = str(latest["classification_type"])
        latest_reason = str(latest.get("reason") or "")
        if latest_type != "non_business_review" and latest_reason != _INITIAL_CLASSIFICATION_REASON:
            continue
        classification = classify_row_with_identity_maps(raw_row, identity_maps)
        new_legacy_type = str(classification["classification_type"])
        if new_legacy_type == "non_business_review":
            continue
        matched_ids = tuple(sorted(set(int(i) for i in classification.get("matched_identity_ids", []))))
        facts = InitialClassificationFacts(
            row_id,
            new_legacy_type,
            matched_ids,
            str(classification.get("reason") or "classification_reason_missing"),
        )
        decision = build_initial_classification(facts)
        if latest_type == decision.classification_type.value and latest_type != "non_business_review":
            continue
        upgraded_ids.add(row_id)
        cursor.execute(
            """UPDATE finance_import_rows
               SET classification_type=%s,
                   matched_identity_ids=%s,
                   resolved_counterparty_account=%s,
                   classification_reason=%s,
                   classified_at=CURRENT_TIMESTAMP
               WHERE id=%s""",
            (
                new_legacy_type,
                _canonical_json(list(matched_ids)),
                classification.get("resolved_counterparty_account"),
                facts.classification_reason,
                row_id,
            ),
        )
        next_version = int(latest["classification_version"]) + 1
        fact_version = int(latest["canonical_fact_version"])
        cursor.execute(
            "INSERT INTO finance_import_classification_events("
            "batch_id,finance_import_row_id,classification_version,canonical_fact_version,"
            "classification_type,disposition,decision_facts_fingerprint,target_identities,"
            "evidence,available_actions,actor,reason) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                batch_id,
                row_id,
                next_version,
                fact_version,
                decision.classification_type.value,
                decision.disposition.value,
                decision.decision_facts_fingerprint.value,
                _canonical_json(decision.target_identities),
                _canonical_json(decision.evidence),
                _canonical_json(decision.available_actions),
                actor.actor_id,
                _INITIAL_CLASSIFICATION_REASON,
            ),
        )


def _persist_ingestion(
    cursor: Any,
    staged: Mapping[str, Any],
    normalized_result: Mapping[str, Any],
    source_digest: str,
    actor: ActorContext,
) -> FinanceWorkbookIngestionReceipt:
    batch_id = int(staged["batch_id"])
    batch_identity = f"finance-import-batch:{batch_id}"
    _insert_batch_contract(cursor, batch_id, batch_identity, source_digest)
    source_warning_count, source_warning_created_count = _append_source_reviews(
        cursor,
        batch_id,
        source_digest,
        normalized_result.get("source_reviews", []),
    )
    canonical_created = _append_missing_classifications(
        cursor, batch_id, staged["staged_rows"], actor
    )
    admitted_rows = len(staged["staged_rows"]) + source_warning_count
    # Staging counts admitted bank rows. Source reviews are appended here.
    if source_warning_count:
        cursor.execute(
            "UPDATE finance_import_batches SET row_count = %s WHERE id = %s",
            (admitted_rows, batch_id),
        )
    _complete_batch(cursor, batch_id)
    source_rows = admitted_rows
    return FinanceWorkbookIngestionReceipt(
        batch_identity,
        source_digest,
        source_rows,
        canonical_created,
        len(staged["staged_rows"]) - canonical_created,
        source_warning_count,
        source_warning_created_count,
    )


def _append_source_reviews(
    cursor: Any,
    batch_id: int,
    source_digest: str,
    source_reviews: object,
) -> tuple[int, int]:
    if not isinstance(source_reviews, list):
        raise ValueError("finance_source_reviews_must_be_array")
    created_count = 0
    for payload in source_reviews:
        if not isinstance(payload, Mapping):
            raise ValueError("finance_source_review_must_be_object")
        issues = payload.get("issue_codes")
        if not isinstance(issues, (list, tuple)):
            raise ValueError("finance_source_review_issues_must_be_array")
        review = build_finance_source_review(
            source_content_digest=source_digest,
            format_id=str(payload.get("format_id")),
            sheet_name=str(payload.get("sheet_name")),
            source_row=int(payload.get("source_row", 0)),
            issue_codes=tuple(str(issue) for issue in issues),
        )
        cursor.execute(
            "INSERT IGNORE INTO finance_import_source_reviews "
            "(review_identity,source_content_digest,format_id,sheet_name,source_row,"
            "source_identity,issue_codes) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                review.review_identity,
                review.source_content_digest,
                review.format_id,
                review.sheet_name,
                review.source_row,
                review.source_identity,
                _canonical_json(review.issue_codes),
            ),
        )
        created = int(cursor.rowcount) == 1
        created_count += int(created)
        cursor.execute(
            "SELECT id FROM finance_import_source_reviews "
            "WHERE review_identity=%s FOR UPDATE",
            (review.review_identity,),
        )
        stored = cursor.fetchone()
        if not isinstance(stored, Mapping):
            raise RuntimeError("finance_source_review_missing_after_insert")
        review_id = int(stored["id"])
        cursor.execute(
            "INSERT IGNORE INTO finance_import_source_review_occurrences "
            "(batch_id,review_id) VALUES (%s,%s)",
            (batch_id, review_id),
        )
        if created:
            cursor.execute(
                "INSERT INTO finance_import_source_review_outbox "
                "(review_id,intent_key) VALUES (%s,%s)",
                (review_id, f"finance-source-review-opened:{review.review_identity}"),
            )
    return len(source_reviews), created_count


def _append_missing_classifications(
    cursor: Any,
    batch_id: int,
    staged_rows: Any,
    actor: ActorContext,
) -> int:
    canonical_created = 0
    for row in _unique_rows(staged_rows):
        if row["result"] == "inserted":
            canonical_created += 1
        if _classification_exists(cursor, int(row["row_id"])):
            continue
        facts = _load_initial_facts(cursor, int(row["row_id"]))
        decision = build_initial_classification(facts)
        _insert_initial_classification(
            cursor,
            batch_id,
            facts.finance_import_row_id,
            decision,
            actor,
        )
        _append_classification_outbox(cursor, batch_id, facts, decision)
    return canonical_created


def _find_replay(cursor: Any, idempotency_key: IdempotencyKey, command_fingerprint: str):
    cursor.execute(
        "SELECT command_fingerprint,result_snapshot FROM "
        "finance_import_ingestion_receipts WHERE idempotency_key=%s FOR UPDATE",
        (idempotency_key.value,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if str(row["command_fingerprint"]) != command_fingerprint:
        raise _IdempotencyConflict()
    snapshot = dict(_json_object(row["result_snapshot"]))
    snapshot.pop("history", None)
    return FinanceWorkbookIngestionReceipt(**snapshot)


def _find_replay_or_attempt(
    cursor: Any,
    idempotency_key: IdempotencyKey,
    command_fingerprint: str,
) -> FinanceWorkbookIngestionReceipt | None:
    receipt = _find_replay(cursor, idempotency_key, command_fingerprint)
    if receipt is not None:
        return receipt
    attempt = _find_attempt(cursor, idempotency_key, command_fingerprint)
    if attempt is not None:
        raise FinanceImportAttemptError(attempt)
    return None


def _find_attempt(
    cursor: Any,
    idempotency_key: IdempotencyKey,
    command_fingerprint: str,
) -> FinanceImportAttempt | None:
    cursor.execute(
        "SELECT * FROM finance_import_ingestion_attempts "
        "WHERE idempotency_key=%s FOR UPDATE",
        (idempotency_key.value,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if str(row["command_fingerprint"]) != command_fingerprint:
        raise _IdempotencyConflict()
    return _attempt_from_row(row)


def _insert_batch_contract(
    cursor: Any, batch_id: int, batch_identity: str, source_digest: str
) -> None:
    cursor.execute(
        "INSERT INTO finance_import_batch_contracts("
        "batch_id,batch_identity,source_content_digest,classifier_version,"
        "fingerprint_version) VALUES (%s,%s,%s,%s,%s)",
        (batch_id, batch_identity, source_digest, _CLASSIFIER_VERSION, _FINGERPRINT_VERSION),
    )


def _classification_exists(cursor: Any, row_id: int) -> bool:
    cursor.execute(
        "SELECT 1 AS present FROM finance_import_classification_events "
        "WHERE finance_import_row_id=%s LIMIT 1",
        (row_id,),
    )
    return cursor.fetchone() is not None


def _load_initial_facts(cursor: Any, row_id: int) -> InitialClassificationFacts:
    cursor.execute(
        "SELECT id,classification_type,matched_identity_ids,classification_reason "
        "FROM finance_import_rows WHERE id=%s",
        (row_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("staged_finance_import_row_missing")
    return InitialClassificationFacts(
        int(row["id"]),
        str(row["classification_type"]),
        _integer_tuple(row["matched_identity_ids"]),
        str(row["classification_reason"] or "classification_reason_missing"),
    )


def _insert_initial_classification(
    cursor: Any, batch_id: int, row_id: int, decision: Any, actor: ActorContext
) -> None:
    cursor.execute(
        "INSERT INTO finance_import_classification_events("
        "batch_id,finance_import_row_id,classification_version,canonical_fact_version,"
        "classification_type,disposition,decision_facts_fingerprint,target_identities,"
        "evidence,available_actions,actor,reason) "
        "VALUES (%s,%s,0,0,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            batch_id,
            row_id,
            decision.classification_type.value,
            decision.disposition.value,
            decision.decision_facts_fingerprint.value,
            _canonical_json(decision.target_identities),
            _canonical_json(decision.evidence),
            _canonical_json(decision.available_actions),
            actor.actor_id,
            _INITIAL_CLASSIFICATION_REASON,
        ),
    )


def _append_classification_outbox(cursor: Any, batch_id: int, facts: Any, decision: Any) -> None:
    event_identity = f"finance-import-classification:{facts.finance_import_row_id}:0"
    payload = {
        "source_event_identity": event_identity,
        "source_version": 0,
        "finance_import_row_id": facts.finance_import_row_id,
        "finance_import_batch_id": batch_id,
        "active": True,
        "integrity_blocker_active": False,
        "amount_delta_ntd": _bank_amount(cursor, facts.finance_import_row_id),
        "affected_order_identities": [],
        "affected_obligation_identities": [],
        "domain_blockers": [_domain_blocker(decision)],
        "reason_codes": list(decision.evidence),
    }
    cursor.execute(
        "INSERT INTO finance_import_outbox(batch_id,intent_key,intent_type,payload_snapshot) "
        "VALUES (%s,%s,'initial_classification_recorded',%s)",
        (batch_id, event_identity, _canonical_json(payload)),
    )


def _bank_amount(cursor: Any, row_id: int) -> int:
    cursor.execute("SELECT credit,debit FROM finance_import_rows WHERE id=%s", (row_id,))
    row = cursor.fetchone()
    amount = (row["credit"] or row["debit"]) if row is not None else 0
    integer_amount = int(amount or 0)
    if integer_amount <= 0 or integer_amount != amount:
        raise ValueError("bank_amount_must_be_positive_integer_ntd")
    return integer_amount


def _domain_blocker(decision: Any) -> str:
    if decision.disposition.value == "manual_review":
        return "classification_requires_review"
    return "classification_target_unresolved"


def _complete_batch(cursor: Any, batch_id: int) -> None:
    cursor.execute(
        "UPDATE finance_import_batches SET status='completed',"
        "completed_at=CURRENT_TIMESTAMP,failure_message=NULL "
        "WHERE id=%s AND status='staged'",
        (batch_id,),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("finance_import_batch_completion_failed")


def _save_receipt(
    cursor: Any,
    idempotency_key: IdempotencyKey,
    command_fingerprint: str,
    receipt: FinanceWorkbookIngestionReceipt,
) -> None:
    batch_id = int(receipt.batch_identity.removeprefix("finance-import-batch:"))
    pending_count = batch_review_count(cursor, batch_id)
    cursor.execute(
        "SELECT EXISTS(SELECT 1 FROM finance_import_integrity_events WHERE batch_id=%s AND active=1) AS blocked",
        (batch_id,),
    )
    history = {"pending_count": pending_count, "blocked": bool(cursor.fetchone()["blocked"])}
    cursor.execute(
        "INSERT INTO finance_import_ingestion_receipts("
        "idempotency_key,command_fingerprint,source_content_digest,batch_id,result_snapshot) "
        "VALUES (%s,%s,%s,%s,%s)",
        (
            idempotency_key.value,
            command_fingerprint,
            receipt.source_content_digest,
            batch_id,
            _canonical_json({**asdict(receipt), "history": history}),
        ),
    )


def _save_success_attempt(
    cursor: Any,
    idempotency_key: IdempotencyKey,
    command_fingerprint: str,
    receipt: FinanceWorkbookIngestionReceipt,
    started_at: datetime,
) -> None:
    cursor.execute(
        "INSERT INTO finance_import_ingestion_attempts("
        "idempotency_key,command_fingerprint,source_content_digest,phase,error_code,"
        "transaction_outcome,batch_id,started_at,completed_at) "
        "VALUES (%s,%s,%s,'completed',NULL,'committed',%s,%s,UTC_TIMESTAMP(6))",
        (
            idempotency_key.value,
            command_fingerprint,
            receipt.source_content_digest,
            int(receipt.batch_identity.removeprefix("finance-import-batch:")),
            started_at,
        ),
    )


def _record_failed_attempt(
    connection_factory: Callable[[], Any],
    idempotency_key: IdempotencyKey,
    command_fingerprint: str,
    source_digest: str,
    phase: str,
    started_at: datetime,
    error_code: str,
) -> FinanceImportAttempt:
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            attempt = _save_or_load_failed_attempt(
                cursor, idempotency_key, command_fingerprint, source_digest,
                phase, started_at, error_code,
            )
        connection.commit()
        return attempt
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _save_or_load_failed_attempt(
    cursor: Any,
    idempotency_key: IdempotencyKey,
    command_fingerprint: str,
    source_digest: str,
    phase: str,
    started_at: datetime,
    error_code: str,
) -> FinanceImportAttempt:
    existing = _find_attempt(cursor, idempotency_key, command_fingerprint)
    if existing is not None:
        return existing
    cursor.execute(
        "INSERT INTO finance_import_ingestion_attempts("
        "idempotency_key,command_fingerprint,source_content_digest,phase,error_code,"
        "transaction_outcome,batch_id,started_at,completed_at) "
        "VALUES (%s,%s,%s,%s,%s,'rolled_back',NULL,%s,UTC_TIMESTAMP(6))",
        (idempotency_key.value, command_fingerprint, source_digest, phase, error_code, started_at),
    )
    attempt = _find_attempt(cursor, idempotency_key, command_fingerprint)
    if attempt is None:
        raise RuntimeError("finance_import_attempt_persistence_failed")
    return attempt


def _attempt_from_row(row: Mapping[str, Any]) -> FinanceImportAttempt:
    batch_id = row.get("batch_id")
    return FinanceImportAttempt(
        attempt_identity=f"finance-import-attempt:{int(row['id'])}",
        source_content_digest=str(row["source_content_digest"]),
        phase=str(row["phase"]),
        error_code=str(row["error_code"]) if row.get("error_code") else None,
        transaction_outcome=str(row["transaction_outcome"]),
        batch_identity=f"finance-import-batch:{int(batch_id)}" if batch_id else None,
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def _attempt_error_code(error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        return "finance_import_source_missing"
    if isinstance(error, ValueError):
        return "finance_import_validation_failed"
    return "finance_import_processing_failed"


def _utc_timestamp() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _unique_rows(staged_rows: Any) -> tuple[Mapping[str, Any], ...]:
    by_id: dict[int, Mapping[str, Any]] = {}
    for row in staged_rows:
        row_id = int(row["row_id"])
        existing = by_id.get(row_id)
        if existing is not None and row["result"] != "inserted":
            continue
        by_id[row_id] = row
    return tuple(by_id[row_id] for row_id in sorted(by_id))


def _integer_tuple(value: Any) -> tuple[int, ...]:
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, list):
        raise ValueError("matched_identity_ids_must_be_array")
    integers = tuple(sorted(set(int(item) for item in payload)))
    if any(item <= 0 for item in integers):
        raise ValueError("matched_identity_ids_must_be_positive")
    return integers


def _validated_source_path(excel_path: Any) -> Path:
    if not isinstance(excel_path, str) or not excel_path.strip():
        raise ValueError("excel_path is required")
    source_path = Path(excel_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"finance workbook not found: {source_path}")
    return source_path


def _source_digest(source_path: Path) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_fingerprint(
    source_digest: str,
    actor: ActorContext,
) -> str:
    payload = {
        "source_content_digest": source_digest,
        "actor_id": actor.actor_id,
    }
    return fingerprint_payload(payload).value


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value: Any) -> dict[str, Any]:
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise RuntimeError("finance_ingestion_receipt_must_be_object")
    return payload


__all__ = ["FinanceImportAttemptError", "ingest_finance_workbook"]
