"""
File: controlled_file_repository.py
Description: 以單一外層交易保存受控檔案 staging、版本與 Apply receipt。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
import uuid

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.controlled_files.contracts import (
    ControlledFileStagingCleanupReason,
    ControlledFileStagingRegistrationStatus,
    ControlledFileStagingResult,
)
from subsystems.controlled_files.workflow import (
    ControlledFileApplyOutcome,
    ControlledFileApplyReceipt,
    ControlledFileCandidate,
    ControlledFileCommandClaim,
    ControlledFileDownloadReference,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
    ControlledFileStagingFacts,
    StoredControlledFileApplyReceipt,
    StageControlledFile,
)
from subsystems.controlled_files.reconciliation import ControlledFileReconciliationEvent
from subsystems.controlled_files.cleanup import (
    CleanupControlledFileStaging,
    ControlledFileCleanupOutcome,
    ControlledFileCleanupReceipt,
    ControlledFileCleanupTerminal,
    StoredControlledFileCleanup,
)


_COMMAND_FAMILY = "controlled_file_apply"
_REGISTERED_STATUS = "registered"
_OWNER_SUBJECT_SQL = {
    ControlledFileOwner.CONTRACT_SIGNING: "SELECT 1 AS present FROM orders WHERE case_no=%s",
    ControlledFileOwner.SCHEDULING: "SELECT 1 AS present FROM orders WHERE case_no=%s",
    ControlledFileOwner.ORDERS: "SELECT 1 AS present FROM orders WHERE case_no=%s",
    ControlledFileOwner.STAFF: (
        "SELECT 1 AS present FROM staff WHERE %s REGEXP '^[1-9][0-9]*$' "
        "AND id=CAST(%s AS UNSIGNED)"
    ),
    ControlledFileOwner.LINE_INTEGRATION: (
        "SELECT 1 AS present FROM line_rich_menu_publications WHERE menu_config_id=%s"
    ),
}


class MySqlControlledFileWorkflowRepository:
    """MySQL adapter; transaction commit remains owned by the workflow UoW."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def register_staging(
        self,
        command: StageControlledFile,
        result: ControlledFileStagingResult,
        *,
        command_fingerprint: PreviewFingerprint,
        created_at: datetime,
    ) -> ControlledFileStagingResult:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _STAGING_INSERT_SQL,
                (
                    result.staging_id,
                    result.staging_id,
                    command.owner.value,
                    command.subject_reference,
                    command.object_key,
                    command.purpose.value,
                    command.logical_folder,
                    result.filename,
                    result.mime_type,
                    result.size_bytes,
                    result.sha256_digest,
                    command.idempotency_key.value,
                    command_fingerprint.value,
                    command.actor.actor_id,
                    _mysql_utc(created_at),
                    _mysql_utc(result.expires_at),
                ),
            )
            if cursor.rowcount == 1:
                return result
            cursor.execute(_STAGING_BY_KEY_SQL, (command.idempotency_key.value,))
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise RuntimeError("controlled_file_staging_registration_missing")
        expected = (
            result.staging_id,
            command_fingerprint.value,
            result.sha256_digest,
            result.size_bytes,
        )
        actual = (
            str(row["staging_id"]),
            str(row["command_fingerprint"]),
            str(row["content_sha256"]),
            int(row["size_bytes"]),
        )
        if actual != expected:
            raise RuntimeError("controlled_file_staging_idempotency_conflict")
        return ControlledFileStagingResult(
            staging_id=str(row["staging_id"]),
            filename=str(row["original_filename"]),
            mime_type=str(row["content_type"]),
            size_bytes=int(row["size_bytes"]),
            sha256_digest=str(row["content_sha256"]),
            expires_at=_aware_utc(row["expires_at_utc"]),
            replayed=True,
        )

    def load_staging(
        self, staging_id: str, *, for_update: bool
    ) -> ControlledFileStagingFacts | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_STAGING_SELECT_SQL + _lock_suffix(for_update), (staging_id,))
            row = cursor.fetchone()
        return None if row is None else _staging_facts(row)

    def owner_subject_exists(
        self, intent: ControlledFileIntent, *, for_update: bool
    ) -> bool:
        statement = _OWNER_SUBJECT_SQL[intent.owner] + _lock_suffix(for_update)
        parameters = (
            (intent.subject_reference, intent.subject_reference)
            if intent.owner is ControlledFileOwner.STAFF
            else (intent.subject_reference,)
        )
        with self._connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchone() is not None

    def find_receipt(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredControlledFileApplyReceipt | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL + _lock_suffix(for_update), (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def claim_command(
        self,
        key: IdempotencyKey,
        command_fingerprint: PreviewFingerprint,
        correlation_id: CorrelationId,
    ) -> ControlledFileCommandClaim:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLAIM_INSERT_SQL,
                (
                    correlation_id.value,
                    _COMMAND_FAMILY,
                    _COMMAND_FAMILY,
                    command_fingerprint.value,
                    key.value,
                ),
            )
            if cursor.rowcount == 1:
                return ControlledFileCommandClaim.CREATED
            cursor.execute(_CLAIM_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise RuntimeError("controlled_file_command_claim_missing")
        matches = (
            str(row["command_family"]) == _COMMAND_FAMILY
            and str(row["aggregate_identity"]) == _COMMAND_FAMILY
            and str(row["command_fingerprint"]) == command_fingerprint.value
        )
        return (
            ControlledFileCommandClaim.MATCHED
            if matches
            else ControlledFileCommandClaim.MISMATCH
        )

    def register_file(
        self,
        candidate: ControlledFileCandidate,
        *,
        actor: ActorContext,
        applied_at: datetime,
    ) -> ControlledFileReadback:
        with self._connection.cursor() as cursor:
            cursor.execute(_STAGING_INTERNAL_SELECT_SQL, (candidate.staging_id,))
            staging = cursor.fetchone()
            if not isinstance(staging, Mapping):
                raise RuntimeError("controlled_file_staging_missing_during_register")
            _require_candidate_matches_staging(candidate, staging)
            cursor.execute(
                _PREDECESSOR_SELECT_SQL,
                (
                    candidate.owner.value,
                    candidate.subject_reference,
                    candidate.object_key,
                    candidate.purpose.value,
                ),
            )
            predecessor = cursor.fetchone()
            version = 1 if predecessor is None else int(predecessor["version_number"]) + 1
            file_id = f"cf_{uuid.uuid4().hex}"
            applied_at_utc = _mysql_utc(applied_at)
            cursor.execute(
                _OBJECT_INSERT_SQL,
                (
                    file_id,
                    int(staging["id"]),
                    candidate.owner.value,
                    candidate.subject_reference,
                    candidate.object_key,
                    candidate.purpose.value,
                    candidate.logical_folder,
                    candidate.filename,
                    str(staging["storage_locator"]),
                    candidate.mime_type,
                    candidate.size_bytes,
                    candidate.sha256_digest,
                    version,
                    None if predecessor is None else int(predecessor["id"]),
                    None if predecessor is None else int(predecessor["version_number"]),
                    actor.actor_id,
                    applied_at_utc,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("controlled_file_registration_insert_failed")
        return _candidate_readback(candidate, file_id, version, applied_at)

    def mark_staging_registered(
        self, staging_id: str, *, expected_version: ExpectedVersion, file_id: str
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _STAGING_MARK_APPLIED_SQL,
                (staging_id, expected_version.value, file_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("controlled_file_staging_state_conflict")

    def save_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredControlledFileApplyReceipt,
        correlation_id: CorrelationId,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _RECEIPT_CONTEXT_SELECT_SQL,
                (stored.receipt.readback.file_id,),
            )
            context = cursor.fetchone()
            if not isinstance(context, Mapping):
                raise RuntimeError("controlled_file_receipt_context_missing")
            preview_fingerprint = _preview_fingerprint_from_context(context)
            snapshot = _receipt_snapshot(stored.receipt)
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (
                    stored.receipt.receipt_id,
                    int(context["staging_object_id"]),
                    int(context["controlled_object_id"]),
                    stored.receipt.receipt_type,
                    stored.receipt.schema_version,
                    key.value,
                    stored.command_fingerprint.value,
                    preview_fingerprint.value,
                    int(context["expected_staging_version"]),
                    _canonical_json(snapshot),
                    str(context["actor_ref"]),
                    correlation_id.value,
                    _mysql_utc(stored.receipt.readback.applied_at),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("controlled_file_receipt_insert_failed")

    def get_readback(self, file_id: str) -> ControlledFileReadback | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_READBACK_SELECT_SQL, (file_id,))
            row = cursor.fetchone()
        return None if row is None else _readback(row)

    def list_readbacks(self) -> tuple[ControlledFileReadback, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_READBACK_LIST_SQL)
            rows = cursor.fetchall()
        return tuple(_readback(row) for row in rows)

    def get_download_reference(
        self, file_id: str
    ) -> ControlledFileDownloadReference | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_DOWNLOAD_SELECT_SQL, (file_id,))
            row = cursor.fetchone()
        if row is None:
            return None
        return ControlledFileDownloadReference(
            readback=_readback(row), staging_id=str(row["staging_id"])
        )

    def get_receipt(self, receipt_id: str) -> ControlledFileApplyReceipt | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_ID_SELECT_SQL, (receipt_id,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row).receipt

    def append_reconciliation_event(
        self, event: ControlledFileReconciliationEvent
    ) -> None:
        snapshot = _canonical_json(
            {
                "schema": "controlled-file-reconciliation-observation.v1",
                "outcome": event.outcome.value,
                "file_id": event.file_id,
                "staging_id": event.staging_id,
                "observed_sha256": event.observed_sha256,
                "observed_size_bytes": event.observed_size_bytes,
            }
        )
        statement = (
            _RECONCILIATION_OBJECT_INSERT_SQL
            if event.file_id is not None
            else _RECONCILIATION_STAGING_INSERT_SQL
        )
        target = event.file_id if event.file_id is not None else event.staging_id
        with self._connection.cursor() as cursor:
            cursor.execute(
                statement,
                (
                    event.event_id,
                    event.outcome.value,
                    event.observation_fingerprint.value,
                    event.observed_sha256,
                    event.observed_size_bytes,
                    snapshot,
                    event.actor.actor_id,
                    event.correlation_id.value,
                    _mysql_utc(event.observed_at),
                    target,
                ),
            )
            if cursor.rowcount == 1:
                return
            cursor.execute(
                "SELECT event_id FROM controlled_file_reconciliation_events "
                "WHERE observation_fingerprint=%s",
                (event.observation_fingerprint.value,),
            )
            replay = cursor.fetchone()
        if not isinstance(replay, Mapping) or str(replay["event_id"]) != event.event_id:
            raise RuntimeError("controlled_file_reconciliation_target_missing")

    def load_cleanup(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredControlledFileCleanup | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLEANUP_SELECT_SQL + _lock_suffix(for_update),
                (key.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        terminal = ControlledFileCleanupTerminal(
            str(row["terminal_type"] or "intent")
        )
        receipt = None
        if terminal is ControlledFileCleanupTerminal.COMPLETED:
            receipt = ControlledFileCleanupReceipt(
                cleanup_id=str(row["cleanup_id"]),
                staging_id=str(row["staging_id"]),
                reason=ControlledFileStagingCleanupReason(str(row["reason"])),
                outcome=ControlledFileCleanupOutcome.CLEANED,
                cleaned_at=_aware_utc(row["terminal_at_utc"]),
            )
        return StoredControlledFileCleanup(
            cleanup_id=str(row["cleanup_id"]),
            command_fingerprint=PreviewFingerprint(str(row["command_fingerprint"])),
            terminal=terminal,
            staging_id=str(row["staging_id"]),
            reason=ControlledFileStagingCleanupReason(str(row["reason"])),
            expected_staging_version=ExpectedVersion(
                int(row["expected_staging_version"])
            ),
            expected_sha256=str(row["expected_sha256"]),
            receipt=receipt,
            error_code=(
                None if row["error_code"] is None else str(row["error_code"])
            ),
        )

    def begin_cleanup(
        self,
        command: CleanupControlledFileStaging,
        *,
        cleanup_id: str,
        command_fingerprint: PreviewFingerprint,
        occurred_at: datetime,
    ) -> StoredControlledFileCleanup:
        event_id = _cleanup_event_id(cleanup_id, 1)
        occurred = _mysql_utc(occurred_at)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLEANUP_INTENT_INSERT_SQL,
                (
                    event_id,
                    cleanup_id,
                    command.reason.value,
                    command.idempotency_key.value,
                    command_fingerprint.value,
                    command.expected_staging_version.value,
                    command.expected_sha256,
                    command.actor.actor_id,
                    command.correlation_id.value,
                    occurred,
                    command.staging_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("controlled_file_cleanup_intent_insert_failed")
            statement = (
                _CLEANUP_CLAIM_EXPIRED_SQL
                if command.reason is ControlledFileStagingCleanupReason.EXPIRED
                else _CLEANUP_CLAIM_ABANDONED_SQL
            )
            parameters = (
                (
                    command.staging_id,
                    command.expected_staging_version.value,
                    command.expected_sha256,
                    occurred,
                )
                if command.reason is ControlledFileStagingCleanupReason.EXPIRED
                else (
                    command.staging_id,
                    command.expected_staging_version.value,
                    command.expected_sha256,
                )
            )
            cursor.execute(statement, parameters)
            if cursor.rowcount != 1:
                raise RuntimeError("controlled_file_cleanup_staging_conflict")
        return StoredControlledFileCleanup(
            cleanup_id=cleanup_id,
            command_fingerprint=command_fingerprint,
            terminal=ControlledFileCleanupTerminal.INTENT,
            staging_id=command.staging_id,
            reason=command.reason,
            expected_staging_version=command.expected_staging_version,
            expected_sha256=command.expected_sha256,
        )

    def complete_cleanup(
        self,
        stored: StoredControlledFileCleanup,
        receipt: ControlledFileCleanupReceipt,
        *,
        occurred_at: datetime,
    ) -> None:
        occurred = _mysql_utc(occurred_at)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLEANUP_COMPLETE_CAS_SQL,
                (
                    occurred,
                    stored.staging_id,
                    stored.expected_staging_version.value + 1,
                    stored.expected_sha256,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("controlled_file_cleanup_terminal_state_conflict")
            cursor.execute(
                _CLEANUP_TERMINAL_INSERT_SQL,
                (
                    _cleanup_event_id(stored.cleanup_id, 2),
                    "completed",
                    occurred,
                    None,
                    stored.cleanup_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("controlled_file_cleanup_terminal_insert_failed")

    def fail_cleanup(
        self,
        stored: StoredControlledFileCleanup,
        *,
        error_code: str,
        occurred_at: datetime,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLEANUP_TERMINAL_INSERT_SQL,
                (
                    _cleanup_event_id(stored.cleanup_id, 2),
                    "reconciliation_required",
                    _mysql_utc(occurred_at),
                    error_code,
                    stored.cleanup_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("controlled_file_cleanup_terminal_insert_failed")


def _staging_facts(row: Mapping[str, object]) -> ControlledFileStagingFacts:
    state = str(row["staging_state"])
    registration = {
        "staged": ControlledFileStagingRegistrationStatus.UNREGISTERED,
        "applied": ControlledFileStagingRegistrationStatus.REGISTERED,
    }.get(state, ControlledFileStagingRegistrationStatus.UNKNOWN)
    return ControlledFileStagingFacts(
        staging=ControlledFileStagingResult(
            staging_id=str(row["staging_id"]),
            filename=str(row["original_filename"]),
            mime_type=str(row["content_type"]),
            size_bytes=int(row["size_bytes"]),
            sha256_digest=str(row["content_sha256"]),
            expires_at=_aware_utc(row["expires_at_utc"]),
            replayed=False,
        ),
        version=int(row["staging_version"]),
        registration_status=registration,
    )


def _candidate_readback(candidate, file_id, version, applied_at):
    return ControlledFileReadback(
        file_id=file_id,
        owner=candidate.owner,
        purpose=candidate.purpose,
        subject_reference=candidate.subject_reference,
        filename=candidate.filename,
        logical_folder=candidate.logical_folder,
        version=version,
        sha256_digest=candidate.sha256_digest,
        mime_type=candidate.mime_type,
        size_bytes=candidate.size_bytes,
        status=_REGISTERED_STATUS,
        applied_at=_aware_utc(applied_at),
    )


def _readback(row: Mapping[str, object]) -> ControlledFileReadback:
    return ControlledFileReadback(
        file_id=str(row["file_id"]),
        owner=ControlledFileOwner(str(row["owner_type"])),
        purpose=ControlledFilePurpose(str(row["purpose"])),
        subject_reference=str(row["subject_reference"]),
        filename=str(row["filename"]),
        logical_folder=str(row["logical_folder"]),
        version=int(row["version_number"]),
        sha256_digest=str(row["content_sha256"]),
        mime_type=str(row["content_type"]),
        size_bytes=int(row["size_bytes"]),
        status=_REGISTERED_STATUS,
        applied_at=_aware_utc(row["applied_at_utc"]),
    )


def _stored_receipt(row: Mapping[str, object]) -> StoredControlledFileApplyReceipt:
    receipt = ControlledFileApplyReceipt(
        receipt_id=str(row["receipt_id"]),
        outcome=ControlledFileApplyOutcome.CREATED,
        readback=_readback(row),
        receipt_type=str(row["command_type"]),
        schema_version=str(row["schema_version"]),
    )
    if _json_value(row["result_snapshot"]) != _receipt_snapshot(receipt):
        raise RuntimeError("controlled_file_receipt_corrupt")
    return StoredControlledFileApplyReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])), receipt
    )


def _receipt_snapshot(receipt: ControlledFileApplyReceipt) -> dict[str, object]:
    readback = receipt.readback
    return {
        "applied_at": _aware_utc(readback.applied_at).isoformat(),
        "file_id": readback.file_id,
        "mime_type": readback.mime_type,
        "logical_folder": readback.logical_folder,
        "outcome": ControlledFileApplyOutcome.CREATED.value,
        "owner": readback.owner.value,
        "purpose": readback.purpose.value,
        "sha256_digest": readback.sha256_digest,
        "size_bytes": readback.size_bytes,
        "status": readback.status,
        "subject_reference": readback.subject_reference,
        "version": readback.version,
    }


def _preview_fingerprint_from_context(row: Mapping[str, object]) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "expires_at": _aware_utc(row["expires_at_utc"]).isoformat(),
            "filename": str(row["filename"]),
            "logical_folder": str(row["logical_folder"]),
            "mime_type": str(row["content_type"]),
            "object_key": str(row["object_key"]),
            "owner": str(row["owner_type"]),
            "purpose": str(row["purpose"]),
            "sha256_digest": str(row["content_sha256"]),
            "size_bytes": int(row["size_bytes"]),
            "staging_id": str(row["staging_id"]),
            "staging_version": int(row["expected_staging_version"]),
            "subject_reference": str(row["subject_reference"]),
        }
    )


def _require_candidate_matches_staging(candidate, row) -> None:
    actual = (
        str(row["staging_id"]),
        int(row["staging_version"]),
        str(row["owner_type"]),
        str(row["subject_reference"]),
        str(row["object_key"]),
        str(row["purpose"]),
        str(row["logical_folder"]),
        str(row["original_filename"]),
        str(row["content_type"]),
        int(row["size_bytes"]),
        str(row["content_sha256"]),
        str(row["staging_state"]),
    )
    expected = (
        candidate.staging_id,
        candidate.staging_version,
        candidate.owner.value,
        candidate.subject_reference,
        candidate.object_key,
        candidate.purpose.value,
        candidate.logical_folder,
        candidate.filename,
        candidate.mime_type,
        candidate.size_bytes,
        candidate.sha256_digest,
        "staged",
    )
    if actual != expected:
        raise RuntimeError("controlled_file_staging_drift_during_register")


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("controlled file time must be datetime")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _mysql_utc(value: datetime) -> datetime:
    return _aware_utc(value).replace(tzinfo=None)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _cleanup_event_id(cleanup_id: str, sequence: int) -> str:
    digest = hashlib.sha256(f"{cleanup_id}:{sequence}".encode("utf-8")).hexdigest()
    return f"cfce_{digest[:32]}"


def _json_value(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


def _lock_suffix(lock: bool) -> str:
    return " FOR UPDATE" if lock else ""


_STAGING_SELECT_SQL = (
    "SELECT staging_id,original_filename,content_type,size_bytes,content_sha256,"
    "staging_state,staging_version,expires_at_utc FROM controlled_file_staging_objects "
    "WHERE staging_id=%s"
)
_STAGING_INSERT_SQL = (
    "INSERT IGNORE INTO controlled_file_staging_objects (staging_id,storage_locator,owner_type,"
    "subject_reference,object_key,purpose,logical_folder,original_filename,content_type,size_bytes,"
    "content_sha256,idempotency_key,command_fingerprint,created_by_actor,created_at_utc,expires_at_utc) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_STAGING_BY_KEY_SQL = (
    "SELECT staging_id,original_filename,content_type,size_bytes,content_sha256,command_fingerprint,"
    "expires_at_utc FROM controlled_file_staging_objects WHERE idempotency_key=%s FOR UPDATE"
)
_STAGING_INTERNAL_SELECT_SQL = (
    "SELECT id,staging_id,storage_locator,owner_type,subject_reference,object_key,purpose,"
    "logical_folder,original_filename,content_type,size_bytes,content_sha256,staging_state,"
    "staging_version FROM controlled_file_staging_objects WHERE staging_id=%s FOR UPDATE"
)
_PREDECESSOR_SELECT_SQL = (
    "SELECT id,version_number FROM controlled_file_objects WHERE owner_type=%s "
    "AND subject_reference=%s AND object_key=%s AND purpose=%s "
    "ORDER BY version_number DESC,id DESC LIMIT 1 FOR UPDATE"
)
_OBJECT_INSERT_SQL = (
    "INSERT INTO controlled_file_objects (opaque_object_id,source_staging_id,owner_type,"
    "subject_reference,object_key,purpose,logical_folder,filename,storage_locator,content_type,"
    "size_bytes,content_sha256,version_number,supersedes_object_id,supersedes_version_number,"
    "created_by_actor,created_at_utc) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_STAGING_MARK_APPLIED_SQL = (
    "UPDATE controlled_file_staging_objects AS s JOIN controlled_file_objects AS o "
    "ON o.source_staging_id=s.id SET s.staging_state='applied',s.applied_at_utc=o.created_at_utc,"
    "s.staging_version=s.staging_version+1 WHERE s.staging_id=%s AND s.staging_state='staged' "
    "AND s.staging_version=%s AND o.opaque_object_id=%s"
)
_CLAIM_INSERT_SQL = (
    "INSERT IGNORE INTO application_command_claims (idempotency_key,command_family,"
    "aggregate_identity,command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)"
)
_CLAIM_SELECT_SQL = (
    "SELECT command_family,aggregate_identity,command_fingerprint FROM application_command_claims "
    "WHERE idempotency_key=%s FOR UPDATE"
)
_READBACK_COLUMNS = (
    "o.opaque_object_id AS file_id,o.owner_type,o.purpose,o.subject_reference,o.filename,"
    "o.logical_folder,o.version_number,o.content_sha256,o.content_type,o.size_bytes,"
    "o.created_at_utc AS applied_at_utc"
)
_READBACK_SELECT_SQL = "SELECT " + _READBACK_COLUMNS + " FROM controlled_file_objects o WHERE o.opaque_object_id=%s"
_READBACK_LIST_SQL = "SELECT " + _READBACK_COLUMNS + " FROM controlled_file_objects o ORDER BY o.id DESC LIMIT 100"
_DOWNLOAD_SELECT_SQL = (
    "SELECT " + _READBACK_COLUMNS + ",s.staging_id FROM controlled_file_objects o "
    "JOIN controlled_file_staging_objects s ON s.id=o.source_staging_id "
    "WHERE o.opaque_object_id=%s"
)
_RECEIPT_SELECT_SQL = (
    "SELECT r.receipt_id,r.command_type,r.schema_version,r.command_fingerprint,r.result_snapshot,"
    + _READBACK_COLUMNS
    + " FROM controlled_file_apply_receipts r JOIN controlled_file_objects o "
    "ON o.id=r.controlled_object_id WHERE r.idempotency_key=%s"
)
_RECEIPT_ID_SELECT_SQL = (
    "SELECT r.receipt_id,r.command_type,r.schema_version,r.command_fingerprint,r.result_snapshot,"
    + _READBACK_COLUMNS
    + " FROM controlled_file_apply_receipts r JOIN controlled_file_objects o "
    "ON o.id=r.controlled_object_id WHERE r.receipt_id=%s"
)
_RECEIPT_CONTEXT_SELECT_SQL = (
    "SELECT s.id AS staging_object_id,o.id AS controlled_object_id,o.created_by_actor AS actor_ref,"
    "s.staging_id,s.staging_version-1 AS expected_staging_version,s.expires_at_utc,"
    "o.owner_type,o.subject_reference,o.object_key,o.purpose,o.logical_folder,o.filename,o.content_type,"
    "o.size_bytes,o.content_sha256 FROM controlled_file_objects o JOIN controlled_file_staging_objects s "
    "ON s.id=o.source_staging_id WHERE o.opaque_object_id=%s FOR UPDATE"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO controlled_file_apply_receipts (receipt_id,staging_object_id,controlled_object_id,"
    "command_type,schema_version,idempotency_key,command_fingerprint,preview_fingerprint,"
    "expected_staging_version,result_snapshot,outcome_state,actor_ref,correlation_id,applied_at_utc) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'created',%s,%s,%s)"
)
_RECONCILIATION_OBJECT_INSERT_SQL = (
    "INSERT IGNORE INTO controlled_file_reconciliation_events (event_id,staging_object_id,"
    "controlled_object_id,outcome,observation_fingerprint,observed_sha256,observed_size_bytes,"
    "observation_snapshot,actor_ref,correlation_id,observed_at_utc) "
    "SELECT %s,s.id,o.id,%s,%s,%s,%s,%s,%s,%s,%s FROM controlled_file_objects o "
    "JOIN controlled_file_staging_objects s ON s.id=o.source_staging_id "
    "WHERE o.opaque_object_id=%s"
)
_RECONCILIATION_STAGING_INSERT_SQL = (
    "INSERT IGNORE INTO controlled_file_reconciliation_events (event_id,staging_object_id,"
    "controlled_object_id,outcome,observation_fingerprint,observed_sha256,observed_size_bytes,"
    "observation_snapshot,actor_ref,correlation_id,observed_at_utc) "
    "SELECT %s,s.id,NULL,%s,%s,%s,%s,%s,%s,%s,%s FROM controlled_file_staging_objects s "
    "WHERE s.staging_id=%s"
)
_CLEANUP_SELECT_SQL = (
    "SELECT intent.cleanup_id,intent.command_fingerprint,intent.reason,"
    "intent.expected_staging_version,intent.expected_sha256,s.staging_id,"
    "terminal.event_type AS terminal_type,terminal.occurred_at_utc AS terminal_at_utc,"
    "terminal.error_code FROM controlled_file_cleanup_events intent "
    "JOIN controlled_file_staging_objects s ON s.id=intent.staging_object_id "
    "LEFT JOIN controlled_file_cleanup_events terminal "
    "ON terminal.cleanup_id=intent.cleanup_id AND terminal.event_sequence=2 "
    "WHERE intent.idempotency_key=%s AND intent.event_sequence=1"
)
_CLEANUP_INTENT_INSERT_SQL = (
    "INSERT INTO controlled_file_cleanup_events (event_id,cleanup_id,staging_object_id,"
    "event_sequence,event_type,reason,idempotency_key,command_fingerprint,"
    "expected_staging_version,expected_sha256,actor_ref,correlation_id,occurred_at_utc,error_code) "
    "SELECT %s,%s,s.id,1,'intent',%s,%s,%s,%s,%s,%s,%s,%s,NULL "
    "FROM controlled_file_staging_objects s WHERE s.staging_id=%s"
)
_CLEANUP_CLAIM_EXPIRED_SQL = (
    "UPDATE controlled_file_staging_objects SET staging_state='quarantined',"
    "staging_version=staging_version+1 WHERE staging_id=%s AND staging_state='staged' "
    "AND staging_version=%s AND content_sha256=%s AND expires_at_utc<=%s"
)
_CLEANUP_CLAIM_ABANDONED_SQL = (
    "UPDATE controlled_file_staging_objects SET staging_state='quarantined',"
    "staging_version=staging_version+1 WHERE staging_id=%s AND staging_state='staged' "
    "AND staging_version=%s AND content_sha256=%s"
)
_CLEANUP_COMPLETE_CAS_SQL = (
    "UPDATE controlled_file_staging_objects SET staging_state='cleaned',"
    "staging_version=staging_version+1,cleaned_at_utc=%s "
    "WHERE staging_id=%s AND staging_state='quarantined' "
    "AND staging_version=%s AND content_sha256=%s"
)
_CLEANUP_TERMINAL_INSERT_SQL = (
    "INSERT INTO controlled_file_cleanup_events (event_id,cleanup_id,staging_object_id,"
    "event_sequence,event_type,reason,idempotency_key,command_fingerprint,"
    "expected_staging_version,expected_sha256,actor_ref,correlation_id,occurred_at_utc,error_code) "
    "SELECT %s,intent.cleanup_id,intent.staging_object_id,2,%s,intent.reason,"
    "intent.idempotency_key,intent.command_fingerprint,intent.expected_staging_version,"
    "intent.expected_sha256,intent.actor_ref,intent.correlation_id,%s,%s "
    "FROM controlled_file_cleanup_events intent "
    "WHERE intent.cleanup_id=%s AND intent.event_sequence=1"
)


ControlledFileWorkflowRepository = MySqlControlledFileWorkflowRepository

__all__ = ["ControlledFileWorkflowRepository", "MySqlControlledFileWorkflowRepository"]
