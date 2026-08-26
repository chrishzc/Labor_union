"""
File: line_media_order_group_repository.py
Description: 以 MySQL 保存 LINE 媒體與群組綁定，並提供 COUNT/LIMIT/OFFSET 唯讀投影。
"""

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
    LineOrderGroupEventPage,
    LineOrderGroupEventRecord,
    LineOrderGroupNumberedPage,
    LineOrderGroupPage,
    OrderLineAudience,
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

    def get_by_group(self, group_id: str) -> LineOrderGroupBindingSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_GROUP_SELECT_BY_GROUP_SQL, (group_id,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _group_snapshot(row)

    def list(self, *, status: str | None, limit: int) -> LineOrderGroupPage:
        clauses = " WHERE binding_status=%s" if status else ""
        parameters: list[object] = [status] if status else []
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM line_order_group_bindings" + clauses,
                parameters,
            )
            total = int((cursor.fetchone() or {}).get("total") or 0)
            cursor.execute(
                f"SELECT case_no,group_id,binding_status,aggregate_version "
                f"FROM line_order_group_bindings{clauses} "
                "ORDER BY updated_at_utc DESC,case_no LIMIT %s",
                [*parameters, limit],
            )
            rows = tuple(cursor.fetchall() or ())
        return LineOrderGroupPage(tuple(_group_snapshot(row) for row in rows), total)

    def list_numbered(
        self,
        *,
        status: str | None,
        page: int,
        page_size: int,
    ) -> LineOrderGroupNumberedPage:
        clauses = " WHERE binding_status=%s" if status else ""
        parameters: list[object] = [status] if status else []
        offset = (page - 1) * page_size
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM line_order_group_bindings" + clauses,
                parameters,
            )
            total = int((cursor.fetchone() or {}).get("total") or 0)
            cursor.execute(
                f"SELECT case_no,group_id,binding_status,aggregate_version "
                f"FROM line_order_group_bindings{clauses} "
                "ORDER BY updated_at_utc DESC,case_no LIMIT %s OFFSET %s",
                [*parameters, page_size, offset],
            )
            rows = tuple(cursor.fetchall() or ())
        return LineOrderGroupNumberedPage(
            tuple(_group_snapshot(row) for row in rows),
            page,
            page_size,
            total,
            (total + page_size - 1) // page_size,
        )

    def events(
        self,
        case_no: str,
        *,
        limit: int,
    ) -> tuple[LineOrderGroupEventRecord, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_GROUP_EVENTS_SQL, (case_no, case_no, limit))
            rows = tuple(cursor.fetchall() or ())
        return tuple(_group_event_record(row) for row in rows)

    def events_numbered(
        self,
        case_no: str,
        *,
        page: int,
        page_size: int,
    ) -> LineOrderGroupEventPage:
        offset = (page - 1) * page_size
        with self._connection.cursor() as cursor:
            cursor.execute(_GROUP_EVENTS_COUNT_SQL, (case_no, case_no))
            total = int((cursor.fetchone() or {}).get("total") or 0)
            cursor.execute(
                _GROUP_EVENTS_NUMBERED_SQL,
                (case_no, case_no, page_size, offset),
            )
            rows = tuple(cursor.fetchall() or ())
        return LineOrderGroupEventPage(
            tuple(_group_event_record(row) for row in rows),
            page,
            page_size,
            total,
            (total + page_size - 1) // page_size,
        )

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
        cursor.execute(
            "INSERT IGNORE INTO line_order_group_bindings (case_no) "
            "SELECT case_no FROM orders WHERE case_no=%s",
            (case_no,),
        )
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

    def sync_participants(self, audience: OrderLineAudience) -> None:
        participants = [
            ("customer", audience.customer_line_user_id.value),
            *(("staff", item.value) for item in audience.staff_line_user_ids),
        ]
        with self._connection.cursor() as cursor:
            for participant_type, line_user_id in participants:
                cursor.execute(
                    _GROUP_PARTICIPANT_UPSERT_SQL,
                    (
                        audience.case_no,
                        participant_type,
                        line_user_id,
                        line_user_id,
                    ),
                )

    def record_invitation_relay(self, relay, idempotency_key) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(_GROUP_RUNTIME_EVENT_BY_KEY_SQL, (idempotency_key.value,))
            existing = optional_row(cursor.fetchone())
            if existing is not None:
                if (
                    str(existing.get("invitation_fingerprint") or "")
                    != relay.invitation_fingerprint.value
                ):
                    raise RuntimeError("line_group_invitation_idempotency_conflict")
                return False
            cursor.execute(
                _GROUP_RUNTIME_EVENT_INSERT_SQL,
                (
                    relay.case_no,
                    "invitation_relayed",
                    None,
                    relay.invitation_fingerprint.value,
                    relay.actor.actor_id,
                    idempotency_key.value,
                    relay.correlation_id.value,
                ),
            )
            cursor.execute(
                "UPDATE line_order_group_bindings SET binding_status='inviting',"
                "last_invitation_at_utc=UTC_TIMESTAMP(6) WHERE case_no=%s",
                (relay.case_no,),
            )
        return True

    def record_membership_event(
        self,
        *,
        group_id,
        line_user_id,
        event_type,
        idempotency_key,
        occurred_at,
    ) -> bool:
        if event_type not in {"member_joined", "member_left"}:
            raise ValueError("LINE group membership event type is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(_GROUP_SELECT_BY_GROUP_SQL + " FOR UPDATE", (group_id,))
            binding = optional_row(cursor.fetchone())
            if binding is None:
                return False
            cursor.execute(_GROUP_RUNTIME_EVENT_BY_KEY_SQL, (idempotency_key.value,))
            if cursor.fetchone():
                return False
            cursor.execute(
                _GROUP_RUNTIME_EVENT_INSERT_SQL,
                (
                    binding["case_no"],
                    event_type,
                    line_user_id.value,
                    None,
                    f"line-user:{line_user_id.value}",
                    idempotency_key.value,
                    idempotency_key.value,
                ),
            )
            participant_status = "joined" if event_type == "member_joined" else "left"
            cursor.execute(
                _GROUP_PARTICIPANT_MEMBERSHIP_SQL,
                (
                    participant_status,
                    participant_status,
                    database_utc(occurred_at),
                    participant_status,
                    database_utc(occurred_at),
                    binding["case_no"],
                    line_user_id.value,
                ),
            )
            cursor.execute(
                _GROUP_STATUS_FROM_MEMBERS_SQL,
                (
                    binding["case_no"],
                    binding["case_no"],
                    binding["case_no"],
                ),
            )
        return True


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


def _group_event_record(row):
    return LineOrderGroupEventRecord(
        int(row["event_id"]),
        str(row["case_no"]),
        str(row["event_type"]),
        str(row["actor_id"]),
        aware_utc(row["occurred_at_utc"]),
        _optional_text(row.get("invitation_fingerprint")),
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
_GROUP_SELECT_BY_GROUP_SQL = (
    "SELECT case_no,group_id,binding_status,aggregate_version "
    "FROM line_order_group_bindings WHERE group_id=%s"
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
_GROUP_PARTICIPANT_UPSERT_SQL = (
    "INSERT INTO line_order_group_participants "
    "(case_no,participant_type,line_user_id,invitation_status) "
    "VALUES (%s,%s,%s,'pending') ON DUPLICATE KEY UPDATE "
    "invitation_status=IF(line_user_id=%s,invitation_status,'pending'),"
    "line_user_id=VALUES(line_user_id)"
)
_GROUP_RUNTIME_EVENT_BY_KEY_SQL = (
    "SELECT invitation_fingerprint FROM line_order_group_runtime_events "
    "WHERE idempotency_key=%s"
)
_GROUP_RUNTIME_EVENT_INSERT_SQL = (
    "INSERT INTO line_order_group_runtime_events "
    "(case_no,event_type,line_user_id,invitation_fingerprint,actor_id,"
    "idempotency_key,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s)"
)
_GROUP_PARTICIPANT_MEMBERSHIP_SQL = (
    "UPDATE line_order_group_participants SET invitation_status=%s,"
    "joined_at_utc=IF(%s='joined',%s,joined_at_utc),"
    "left_at_utc=IF(%s='left',%s,left_at_utc) "
    "WHERE case_no=%s AND line_user_id=%s"
)
_GROUP_STATUS_FROM_MEMBERS_SQL = (
    "UPDATE line_order_group_bindings SET binding_status=IF("
    "(SELECT COUNT(*) FROM line_order_group_participants "
    "WHERE case_no=%s AND invitation_status<>'joined')=0,'active','attention'),"
    "activated_at_utc=IF((SELECT COUNT(*) FROM line_order_group_participants "
    "WHERE case_no=%s AND invitation_status<>'joined')=0,UTC_TIMESTAMP(6),"
    "activated_at_utc) WHERE case_no=%s"
)
_GROUP_EVENTS_SQL = (
    "SELECT event_id,case_no,event_type,actor_id,occurred_at_utc,"
    "invitation_fingerprint FROM (SELECT id AS event_id,case_no,action AS "
    "event_type,actor_id,occurred_at_utc,NULL AS invitation_fingerprint FROM "
    "line_order_group_binding_events WHERE case_no=%s UNION ALL SELECT id AS "
    "event_id,case_no,event_type,actor_id,occurred_at_utc,invitation_fingerprint "
    "FROM line_order_group_runtime_events WHERE case_no=%s) events "
    "ORDER BY occurred_at_utc DESC,event_id DESC LIMIT %s"
)
_GROUP_EVENTS_NUMBERED_SQL = _GROUP_EVENTS_SQL + " OFFSET %s"
_GROUP_EVENTS_COUNT_SQL = (
    "SELECT COUNT(*) AS total FROM (SELECT id FROM "
    "line_order_group_binding_events WHERE case_no=%s UNION ALL SELECT id FROM "
    "line_order_group_runtime_events WHERE case_no=%s) events"
)


__all__ = [
    "MySqlLineMediaMetadataRepository",
    "MySqlLineOrderGroupBindingRepository",
]
