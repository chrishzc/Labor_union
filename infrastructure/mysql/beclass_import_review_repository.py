"""MySQL persistence for invalid BeClass rows and review resolution."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from typing import Iterator, Mapping

from pymysql.err import IntegrityError, OperationalError

from domains.case_import.beclass_import_review import (
    BeClassImportReviewFacts,
    BeClassImportReviewStatus,
    BeClassImportSourceKind,
    InvalidBeClassImportRow,
    review_outbox_snapshot,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.case_import.beclass_import_review_workflow import (
    ApplyBeClassImportReview,
    BeClassImportReviewClaimState,
    BeClassImportReviewReceipt,
    BeClassImportReviewStorageError,
    StoredBeClassImportReviewReceipt,
)

_COMMAND_FAMILY = "beclass_import_review"
_RETRYABLE_MYSQL_CODES = frozenset({1062, 1205, 1213})


class BeClassImportReviewMySqlUnitOfWork(MySqlUnitOfWork):
    def __enter__(self):
        try:
            return super().__enter__()
        except OperationalError as error:
            _raise_storage_error(error)

    def commit(self) -> None:
        try:
            super().commit()
        except OperationalError as error:
            _raise_storage_error(error)


class MySqlBeClassImportReviewRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    # Kept cohesive so invalid-row evidence and its alert intent stay atomic.
    def append_invalid_row(self, root: InvalidBeClassImportRow) -> int:
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _ROOT_INSERT_SQL,
                (
                    root.review_identity,
                    root.source_kind.value,
                    root.source_event_identity,
                    root.source_sheet,
                    root.source_row,
                    root.masked_identifier,
                    root.source_fingerprint.value,
                    _canonical_json(root.source_payload),
                    _canonical_json(root.issue_codes),
                ),
            )
            review_row_id = int(cursor.lastrowid or 0)
            if review_row_id <= 0:
                raise RuntimeError("beclass_import_review_row_insert_failed")
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                (
                    review_row_id,
                    None,
                    _opened_intent_key(root),
                    "review_opened",
                    _canonical_json(review_outbox_snapshot(root)),
                ),
            )
        return review_row_id

    def load(self, review_identity, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_REVIEW_SELECT_SQL + suffix, (review_identity,))
            row = cursor.fetchone()
        return None if row is None else _facts(row)

    def claim_command(self, command, command_fingerprint):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _CLAIM_INSERT_SQL,
                (
                    command.idempotency_key.value,
                    _COMMAND_FAMILY,
                    command.intent.review_identity,
                    command_fingerprint.value,
                    command.correlation_id.value,
                ),
            )
            if int(cursor.rowcount) == 1:
                return BeClassImportReviewClaimState.CREATED
            return _load_claim_state(cursor, command, command_fingerprint)

    def find_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    # Kept cohesive because all fields form one immutable resolution event.
    def append_resolution_event(self, command, candidate, write_receipt) -> int:
        with _mysql_cursor(self._connection) as cursor:
            review_row_id = _review_row_id(
                cursor,
                candidate.review_identity,
                lock=True,
            )
            cursor.execute(
                _EVENT_INSERT_SQL,
                (
                    review_row_id,
                    candidate.resulting_version - 1,
                    candidate.resulting_version,
                    candidate.fingerprint.value,
                    write_receipt.owning_record_identity,
                    _canonical_json(candidate.corrected_payload),
                    _canonical_json(candidate.resolved_issue_codes),
                    command.actor.actor_id,
                    command.reason,
                    command.correlation_id.value,
                    command.idempotency_key.value,
                ),
            )
            event_id = int(cursor.lastrowid or 0)
        if event_id <= 0:
            raise RuntimeError("beclass_import_review_event_insert_failed")
        return event_id

    # Kept cohesive because the bounded payload and owning event form one intent.
    def append_outbox(self, candidate, review_event_id) -> int:
        with _mysql_cursor(self._connection) as cursor:
            review_row_id = _review_row_id(
                cursor,
                candidate.review_identity,
                lock=False,
            )
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                (
                    review_row_id,
                    review_event_id,
                    _resolved_intent_key(candidate),
                    "review_resolved",
                    _canonical_json(review_outbox_snapshot(candidate)),
                ),
            )
            outbox_id = int(cursor.lastrowid or 0)
        if outbox_id <= 0:
            raise RuntimeError("beclass_import_review_outbox_insert_failed")
        return outbox_id

    # Kept cohesive because receipt columns mirror one replay evidence payload.
    def save_receipt(self, key, stored) -> None:
        receipt = stored.receipt
        with _mysql_cursor(self._connection) as cursor:
            review_row_id = _review_row_id(
                cursor,
                receipt.review_identity,
                lock=False,
            )
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (
                    key.value,
                    stored.command_fingerprint.value,
                    receipt.preview_fingerprint.value,
                    review_row_id,
                    receipt.owning_record_identity,
                    receipt.review_event_id,
                    receipt.outbox_id,
                    receipt.resulting_version,
                    _canonical_json(_receipt_payload(receipt)),
                ),
            )


@contextmanager
def _mysql_cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except (OperationalError, IntegrityError) as error:
        _raise_storage_error(error)


def _raise_storage_error(error):
    code = int(error.args[0]) if error.args else 0
    raise BeClassImportReviewStorageError(
        "BeClass import review MySQL transaction failed.",
        retryable=code in _RETRYABLE_MYSQL_CODES,
    ) from error


# Kept cohesive so root and latest event are validated as one consistent read.
def _facts(row):
    source_payload = _json_object(row["source_payload"])
    issue_codes = _json_text_tuple(row["issue_codes"])
    root = InvalidBeClassImportRow(
        str(row["review_identity"]),
        BeClassImportSourceKind(str(row["source_kind"])),
        str(row["source_event_identity"]),
        str(row["source_sheet"]),
        int(row["source_row"]),
        str(row["masked_identifier"]),
        source_payload,
        issue_codes,
        PreviewFingerprint(str(row["source_fingerprint"])),
    )
    corrected_payload = row.get("corrected_payload")
    if corrected_payload is None:
        return BeClassImportReviewFacts(
            root,
            0,
            BeClassImportReviewStatus.OPEN,
            source_payload,
        )
    return BeClassImportReviewFacts(
        root,
        int(row["resulting_version"]),
        BeClassImportReviewStatus.RESOLVED,
        _json_object(corrected_payload),
    )


def _review_row_id(cursor, review_identity, *, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT id FROM beclass_import_review_rows WHERE review_identity=%s" + suffix,
        (review_identity,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise RuntimeError("beclass_import_review_row_not_found")
    return int(row["id"])


def _load_claim_state(cursor, command, fingerprint):
    cursor.execute(
        "SELECT command_family,aggregate_identity,command_fingerprint "
        "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
        (command.idempotency_key.value,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise RuntimeError("beclass_import_review_command_claim_missing")
    matches = (
        str(row["command_family"]) == _COMMAND_FAMILY
        and str(row["aggregate_identity"]) == command.intent.review_identity
        and str(row["command_fingerprint"]) == fingerprint.value
    )
    if matches:
        return BeClassImportReviewClaimState.MATCHED
    return BeClassImportReviewClaimState.MISMATCH


def _stored_receipt(row):
    receipt = BeClassImportReviewReceipt(
        str(row["review_identity"]),
        str(row["owning_record_identity"]),
        int(row["resulting_version"]),
        int(row["review_event_id"]),
        int(row["outbox_id"]),
        PreviewFingerprint(str(row["preview_fingerprint"])),
    )
    if _json_object(row["result_snapshot"]) != _receipt_payload(receipt):
        raise RuntimeError("beclass_import_review_receipt_corrupt")
    return StoredBeClassImportReviewReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _receipt_payload(receipt):
    return {
        "outbox_id": receipt.outbox_id,
        "owning_record_identity": receipt.owning_record_identity,
        "resulting_version": receipt.resulting_version,
        "review_event_id": receipt.review_event_id,
        "review_identity": receipt.review_identity,
    }


def _opened_intent_key(root):
    return _hashed_identity("beclass-review-opened", root.source_fingerprint.value)


def _resolved_intent_key(candidate):
    return _hashed_identity("beclass-review-resolved", candidate.fingerprint.value)


def _hashed_identity(prefix, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise RuntimeError("BeClass import review payload must be an object")
    return dict(parsed)


def _json_text_tuple(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise RuntimeError("BeClass import review issue codes must be an array")
    return tuple(sorted(str(item) for item in parsed))


_ROOT_INSERT_SQL = (
    "INSERT INTO beclass_import_review_rows "
    "(review_identity,source_kind,source_event_identity,source_sheet,source_row,"
    "masked_identifier,source_fingerprint,source_payload,issue_codes) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_REVIEW_SELECT_SQL = (
    "SELECT root.review_identity,root.source_kind,root.source_event_identity,"
    "root.source_sheet,root.source_row,root.masked_identifier,"
    "root.source_fingerprint,root.source_payload,root.issue_codes,"
    "event.resulting_version,event.corrected_payload "
    "FROM beclass_import_review_rows AS root "
    "LEFT JOIN beclass_import_review_events AS event ON event.id=("
    "SELECT MAX(latest.id) FROM beclass_import_review_events AS latest "
    "WHERE latest.review_row_id=root.id) WHERE root.review_identity=%s"
)
_CLAIM_INSERT_SQL = (
    "INSERT IGNORE INTO application_command_claims "
    "(idempotency_key,command_family,aggregate_identity,"
    "command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)"
)
_EVENT_INSERT_SQL = (
    "INSERT INTO beclass_import_review_events "
    "(review_row_id,event_type,expected_version,resulting_version,"
    "candidate_fingerprint,owning_record_identity,corrected_payload,"
    "resolved_issue_codes,actor,reason,"
    "correlation_id,idempotency_key) "
    "VALUES (%s,'resolved',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO beclass_import_review_outbox "
    "(review_row_id,review_event_id,intent_key,intent_type,bounded_snapshot) "
    "VALUES (%s,%s,%s,%s,%s)"
)
_RECEIPT_SELECT_SQL = (
    "SELECT receipt.command_fingerprint,receipt.preview_fingerprint,"
    "root.review_identity,receipt.owning_record_identity,"
    "receipt.resulting_version,receipt.review_event_id,"
    "receipt.outbox_id,receipt.result_snapshot "
    "FROM beclass_import_review_receipts AS receipt "
    "JOIN beclass_import_review_rows AS root ON root.id=receipt.review_row_id "
    "WHERE receipt.idempotency_key=%s FOR UPDATE"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO beclass_import_review_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,review_row_id,"
    "owning_record_identity,review_event_id,outbox_id,resulting_version,"
    "result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)


__all__ = [
    "BeClassImportReviewMySqlUnitOfWork",
    "MySqlBeClassImportReviewRepository",
]
