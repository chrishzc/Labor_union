"""MySQL adapters for LINE media metadata and order-group bindings."""

from __future__ import annotations

from typing import Any

from pymysql.err import IntegrityError

from domains.line.identities import LineGroupId
from domains.line.media import LineMediaCategory, LineMediaMetadata
from domains.line.order_group import (
    LineOrderGroupBindingSnapshot,
    LineOrderGroupBindingStatus,
    build_order_group_binding_candidate,
)
from infrastructure.mysql.line_repository_support import (
    aware_utc,
    database_utc,
    mysql_error_code,
    optional_row,
    source_identity,
)
from shared_kernel.identities import ExpectedVersion
from subsystems.line.media_contracts import (
    ArchiveLineMediaResult,
    LineMediaArchiveOutcome,
)
from subsystems.line.order_group_contracts import (
    BindLineOrderGroupCommand,
    BindLineOrderGroupResult,
    LineOrderGroupCommandOutcome,
)


class MySqlLineMediaMetadataRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, provider_media_id: str) -> LineMediaMetadata | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_MEDIA_SELECT_SQL, (provider_media_id,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _media_metadata(row)

    def register(
        self,
        metadata: LineMediaMetadata,
        object_reference: str,
        idempotency_key,
    ) -> ArchiveLineMediaResult:
        try:
            self._insert(metadata, object_reference, idempotency_key.value)
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            return self._existing_registration(metadata, idempotency_key.value)
        return ArchiveLineMediaResult(
            LineMediaArchiveOutcome.CREATED,
            metadata,
            object_reference,
        )

    def _insert(self, metadata, object_reference, idempotency_key):
        source = metadata.source
        with self._connection.cursor() as cursor:
            cursor.execute(
                _MEDIA_INSERT_SQL,
                (
                    metadata.provider_media_id,
                    source.source_type.value,
                    source.source_id,
                    source.user_id.value if source.user_id else None,
                    metadata.content_type,
                    metadata.size_bytes,
                    metadata.content_sha256,
                    database_utc(metadata.received_at),
                    metadata.category.value,
                    metadata.owner_type,
                    metadata.owner_reference,
                    object_reference,
                    idempotency_key,
                ),
            )

    def _existing_registration(self, metadata, idempotency_key):
        with self._connection.cursor() as cursor:
            cursor.execute(_MEDIA_SELECT_BY_KEY_SQL, (idempotency_key,))
            row = optional_row(cursor.fetchone())
        if row is None:
            raise RuntimeError("line_media_duplicate_missing")
        existing = _media_metadata(row)
        if existing != metadata:
            raise RuntimeError("line_media_idempotency_conflict")
        return ArchiveLineMediaResult(
            LineMediaArchiveOutcome.EXISTING,
            existing,
            str(row["object_reference"]),
        )


class MySqlLineOrderGroupBindingRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, case_no: str) -> LineOrderGroupBindingSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_GROUP_SELECT_SQL, (case_no,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _group_snapshot(row)

    def bind(
        self,
        command: BindLineOrderGroupCommand,
    ) -> BindLineOrderGroupResult:
        with self._connection.cursor() as cursor:
            existing = self._existing_event(cursor, command.idempotency_key.value)
            if existing is not None:
                return self._existing_result(existing, command)
            snapshot = self._locked_snapshot(cursor, command.case_no)
            candidate = build_order_group_binding_candidate(
                snapshot,
                group_id=command.group_id,
                expected_version=command.expected_version,
                actor=command.actor,
            )
            try:
                cursor.execute(
                    _GROUP_UPDATE_SQL,
                    (
                        command.group_id.value,
                        candidate.resulting_version.value,
                        command.case_no,
                        candidate.expected_version.value,
                    ),
                )
            except IntegrityError as error:
                if mysql_error_code(error) != 1062:
                    raise
                raise RuntimeError("line_group_already_bound_to_another_order") from error
            if cursor.rowcount != 1:
                raise RuntimeError("line_order_group_binding_conflict")
            self._append_event(cursor, command, candidate)
        return BindLineOrderGroupResult(LineOrderGroupCommandOutcome.CREATED, candidate)

    def _locked_snapshot(self, cursor, case_no):
        cursor.execute(_GROUP_SELECT_SQL + " FOR UPDATE", (case_no,))
        row = optional_row(cursor.fetchone())
        if row is None:
            raise LookupError("line_order_group_not_found")
        return _group_snapshot(row)

    def _existing_event(self, cursor, key):
        cursor.execute(_GROUP_EVENT_SELECT_SQL, (key,))
        return optional_row(cursor.fetchone())

    def _existing_result(self, row, command):
        before_group_id = row.get("before_group_id")
        before_snapshot = LineOrderGroupBindingSnapshot(
            str(row["case_no"]),
            LineGroupId(str(before_group_id)) if before_group_id else None,
            LineOrderGroupBindingStatus.UNBOUND
            if before_group_id is None
            else LineOrderGroupBindingStatus.BOUND,
            ExpectedVersion(int(row["expected_version"])),
        )
        candidate = build_order_group_binding_candidate(
            before_snapshot,
            group_id=command.group_id,
            expected_version=command.expected_version,
            actor=command.actor,
        )
        if str(row["binding_fingerprint"]) != candidate.fingerprint.value:
            raise RuntimeError("line_order_group_idempotency_conflict")
        if str(row["resulting_group_id"]) != command.group_id.value:
            raise RuntimeError("line_order_group_idempotency_conflict")
        return BindLineOrderGroupResult(LineOrderGroupCommandOutcome.EXISTING, candidate)

    def _append_event(self, cursor, command, candidate):
        action = "bound" if candidate.before_group_id is None else "replaced"
        cursor.execute(
            _GROUP_EVENT_INSERT_SQL,
            (
                command.case_no,
                action,
                candidate.before_group_id.value if candidate.before_group_id else None,
                candidate.resulting_group_id.value,
                candidate.expected_version.value,
                candidate.resulting_version.value,
                command.actor.actor_id,
                candidate.fingerprint.value,
                command.idempotency_key.value,
                command.correlation_id.value,
            ),
        )


def _media_metadata(row):
    return LineMediaMetadata(
        provider_media_id=str(row["provider_media_id"]),
        source=source_identity(
            str(row["source_type"]),
            str(row["source_identity"]),
            _optional_text(row.get("source_user_id")),
        ),
        content_type=str(row["content_type"]),
        size_bytes=int(row["size_bytes"]),
        content_sha256=str(row["content_sha256"]),
        received_at=aware_utc(row["received_at_utc"]),
        category=LineMediaCategory(str(row["media_category"])),
        owner_type=_optional_text(row.get("owner_type")),
        owner_reference=_optional_text(row.get("owner_reference")),
    )


def _group_snapshot(row):
    group_id = row.get("group_id")
    return LineOrderGroupBindingSnapshot(
        str(row["case_no"]),
        LineGroupId(str(group_id)) if group_id is not None else None,
        LineOrderGroupBindingStatus(str(row["binding_status"])),
        ExpectedVersion(int(row["aggregate_version"])),
    )


def _optional_text(value):
    return None if value is None else str(value)


_MEDIA_COLUMNS = (
    "provider_media_id,source_type,source_identity,source_user_id,content_type,"
    "size_bytes,content_sha256,received_at_utc,media_category,owner_type,"
    "owner_reference,object_reference"
)
_MEDIA_SELECT_SQL = (
    f"SELECT {_MEDIA_COLUMNS} FROM line_media_records WHERE provider_media_id=%s"
)
_MEDIA_SELECT_BY_KEY_SQL = (
    f"SELECT {_MEDIA_COLUMNS} FROM line_media_records WHERE idempotency_key=%s"
)
_MEDIA_INSERT_SQL = (
    "INSERT INTO line_media_records (provider_media_id,source_type,source_identity,"
    "source_user_id,content_type,size_bytes,content_sha256,received_at_utc,"
    "media_category,owner_type,owner_reference,object_reference,idempotency_key) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_GROUP_SELECT_SQL = (
    "SELECT case_no,group_id,binding_status,aggregate_version "
    "FROM line_order_group_bindings WHERE case_no=%s"
)
_GROUP_UPDATE_SQL = (
    "UPDATE line_order_group_bindings SET group_id=%s,binding_status='bound',"
    "aggregate_version=%s WHERE case_no=%s AND aggregate_version=%s"
)
_GROUP_EVENT_SELECT_SQL = (
    "SELECT case_no,before_group_id,resulting_group_id,expected_version,"
    "binding_fingerprint FROM line_order_group_binding_events "
    "WHERE idempotency_key=%s"
)
_GROUP_EVENT_INSERT_SQL = (
    "INSERT INTO line_order_group_binding_events (case_no,action,before_group_id,"
    "resulting_group_id,expected_version,resulting_version,actor_id,"
    "binding_fingerprint,idempotency_key,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)


__all__ = [
    "MySqlLineMediaMetadataRepository",
    "MySqlLineOrderGroupBindingRepository",
]
