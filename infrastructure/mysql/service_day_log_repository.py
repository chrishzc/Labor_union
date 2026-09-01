"""
File: service_day_log_repository.py
Description: 以正式指派與已保存 LINE media 驗證月嫂服務日日誌，並同交易寫入 Scheduling event/outbox。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from domains.controlled_files.reference_finalize import (
    ControlledFileFinalizeIntent,
    SchedulingControlledFileReference,
    canonical_scheduling_object_key,
)
from infrastructure.db.controlled_file_reference_finalize_repository import (
    MySqlControlledFileReferenceFinalizeRepository,
)
from subsystems.scheduling.service_day_log_workflow import (
    ApplyServiceDayLog,
    ControlledServiceDayLogAttachment,
    ServiceDayLogResult,
)


class MySqlServiceDayLogRepository:
    def __init__(self, connection, *, reference_finalize_repository=None) -> None:
        self._connection = connection
        # The supplied connection belongs to the outer Scheduling application;
        # this adapter only executes statements and never commits or rolls back.
        self._reference_finalize_repository = (
            reference_finalize_repository
            or MySqlControlledFileReferenceFinalizeRepository(connection)
        )

    def load_assignment(
        self, staff_id: int, assignment_id: int, service_date, *, for_update: bool
    ):
        with self._connection.cursor() as cursor:
            query = _ASSIGNMENT_LOCK_SQL if for_update else _ASSIGNMENT_QUERY_SQL
            cursor.execute(query, (staff_id, assignment_id, service_date))
            row = cursor.fetchone()
        if not isinstance(row, dict):
            raise ValueError("service_day_assignment_not_visible")
        required = row.get("requires_cooking")
        if required is None:
            return {**row, "requires_cooking": None}
        return {**row, "requires_cooking": bool(required)}

    def submit(self, command: ApplyServiceDayLog, assignment) -> ServiceDayLogResult:
        fingerprint = command.preview_fingerprint.value
        existing = self._existing(command.idempotency_key)
        if existing is not None:
            return self._existing_result(existing, command, fingerprint)
        existing_for_day = self._existing_for_assignment_day(
            command.assignment_id, command.intent.service_date
        )
        if existing_for_day is not None:
            return self._existing_result(existing_for_day, command, fingerprint)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _LOG_INSERT_SQL,
                (
                    assignment["case_no"], command.assignment_id, command.staff_id,
                    command.line_user_id, command.intent.service_date,
                    command.intent.baby_log_text.strip(), assignment["requires_cooking"],
                    fingerprint, command.idempotency_key,
                ),
            )
            log_id = int(cursor.lastrowid)
            cursor.execute(
                _EVENT_INSERT_SQL,
                (log_id, command.assignment_id, command.staff_id, command.intent.service_date, command.idempotency_key),
            )
            event_id = int(cursor.lastrowid)
            controlled_attachments = self._attach_controlled_files(command, log_id)
            payload = json.dumps(
                {
                    "case_no": assignment["case_no"],
                    "assignment_id": command.assignment_id,
                    "service_date": command.intent.service_date.isoformat(),
                    "requires_cooking": assignment["requires_cooking"],
                    "controlled_file_finalize_ids": [
                        finalize_id for _, finalize_id in controlled_attachments
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            cursor.execute(_OUTBOX_INSERT_SQL, (event_id, f"scheduling-service-day-log:{log_id}", payload))
        return ServiceDayLogResult(
            log_id,
            str(assignment["case_no"]),
            command.assignment_id,
            command.intent.service_date.isoformat(),
            command.intent.baby_log_text.strip(),
            bool(assignment["requires_cooking"]),
            "created",
            tuple(command.controlled_file_attachments),
        )

    def _attach_controlled_files(
        self, command: ApplyServiceDayLog, log_id: int
    ) -> tuple[tuple[int, str], ...]:
        """Write 1015 attachment/reference/intent facts in this UoW only."""

        if not command.controlled_file_attachments:
            return ()
        created_at = datetime.now(timezone.utc)
        result: list[tuple[int, str]] = []
        for attachment in command.controlled_file_attachments:
            expected_object_key = canonical_scheduling_object_key(
                assignment_id=command.assignment_id,
                service_date=command.intent.service_date,
                attachment_kind=attachment.attachment_kind,
                sequence=attachment.sequence,
                sha256_digest=attachment.sha256_digest,
            )
            self._assert_canonical_scheduling_object(
                attachment, expected_object_key
            )
            self._reference_finalize_repository.assert_controlled_file_exists(
                attachment.controlled_file_object_id
            )
            with self._connection.cursor() as cursor:
                cursor.execute(
                    _CONTROLLED_ATTACHMENT_INSERT_SQL,
                    (
                        log_id,
                        attachment.attachment_kind,
                        attachment.controlled_file_object_id,
                        attachment.staging_id,
                        expected_object_key,
                        attachment.sha256_digest,
                        attachment.attachment_kind,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError(
                        "service_day_log_controlled_file_attachment_create_conflict"
                    )
                attachment_id = int(cursor.lastrowid)
            reference_id = f"cfrf_{uuid4().hex}"
            finalize_id = f"cff_{uuid4().hex}"
            self._reference_finalize_repository.create_scheduling_reference(
                SchedulingControlledFileReference(
                    reference_id=reference_id,
                    controlled_file_object_id=attachment.controlled_file_object_id,
                    service_day_log_attachment_id=attachment_id,
                    created_at=attachment.created_at or created_at,
                )
            )
            self._reference_finalize_repository.create_finalize_intent(
                ControlledFileFinalizeIntent(
                    finalize_id=finalize_id,
                    staging_id=attachment.staging_id,
                    controlled_file_object_id=attachment.controlled_file_object_id,
                    expected_sha256=attachment.sha256_digest,
                    created_at=attachment.created_at or created_at,
                )
            )
            result.append((attachment_id, finalize_id))
        return tuple(result)

    def _assert_canonical_scheduling_object(
        self, attachment, expected_object_key: str
    ) -> None:
        """Reject an arbitrary ``cf_`` object before any attachment write."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                _CANONICAL_SCHEDULING_OBJECT_SQL,
                (attachment.controlled_file_object_id, attachment.staging_id),
            )
            row = cursor.fetchone()
        if not isinstance(row, dict):
            raise ValueError("service_day_log_controlled_file_object_not_found")
        if (
            str(row.get("object_key")) != expected_object_key
            or str(row.get("content_sha256")) != attachment.sha256_digest
            or str(row.get("owner_type")) != "scheduling"
            or str(row.get("purpose")) != attachment.attachment_kind
        ):
            raise ValueError("service_day_log_controlled_file_object_key_mismatch")

    def load_replay(self, command: ApplyServiceDayLog) -> ServiceDayLogResult | None:
        existing = self._existing(command.idempotency_key)
        if existing is None:
            return None
        return self._existing_result(
            existing, command, command.preview_fingerprint.value
        )

    def _existing(self, key: str):
        with self._connection.cursor() as cursor:
            cursor.execute(_EXISTING_SQL, (key,))
            return cursor.fetchone()

    def _existing_for_assignment_day(self, assignment_id: int, service_date):
        with self._connection.cursor() as cursor:
            cursor.execute(_EXISTING_FOR_ASSIGNMENT_DAY_SQL, (assignment_id, service_date))
            return cursor.fetchone()

    def _existing_result(self, row, command, fingerprint: str):
        if (
            int(row["assignment_id"]) != command.assignment_id
            or int(row["staff_id"]) != command.staff_id
            or str(row["staff_line_user_id"]) != command.line_user_id
            or str(row["content_fingerprint"]) != fingerprint
        ):
            raise ValueError("service_day_log_idempotency_conflict")
        return _result_from_row(
            row,
            outcome="existing",
            attachments=self._load_controlled_attachments(int(row["id"])),
        )

    def load_for_staff(
        self, log_id: int, staff_id: int, line_user_id: str
    ) -> ServiceDayLogResult | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_READBACK_SQL, (log_id, staff_id, line_user_id))
            row = cursor.fetchone()
        if not isinstance(row, dict):
            return None
        return _result_from_row(
            row,
            outcome="existing",
            attachments=self._load_controlled_attachments(int(row["id"])),
        )


    def _load_controlled_attachments(self, log_id: int) -> tuple[ControlledServiceDayLogAttachment, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_ATTACHMENTS_READBACK_SQL, (log_id,))
            fetchall = getattr(cursor, "fetchall", None)
            rows = fetchall() if callable(fetchall) else ()
        return tuple(
            ControlledServiceDayLogAttachment(
                str(row["controlled_file_object_id"]),
                str(row["staging_id"]),
                str(row["content_sha256"]),
                str(row["attachment_kind"]),
                index,
            )
            for index, row in enumerate(rows, start=1)
            if isinstance(row, dict)
        )


def _result_from_row(row, *, outcome: str, attachments=()) -> ServiceDayLogResult:
    if row.get("requires_cooking") is None:
        raise ValueError("service_day_log_cooking_requirement_unresolved")
    return ServiceDayLogResult(
        int(row["id"]),
        str(row["case_no"]),
        int(row["assignment_id"]),
        str(row["service_date"]),
        str(row["baby_log_text"]),
        bool(row["requires_cooking"]),
        outcome,
        tuple(attachments),
    )


_ASSIGNMENT_QUERY_SQL = (
    "SELECT csa.case_no,o.requires_cooking FROM staff_schedule ss "
    "JOIN case_staff_assignments csa ON csa.id=ss.assignment_id "
    "JOIN orders o ON o.case_no=csa.case_no "
    "WHERE csa.staff_id=%s AND csa.id=%s AND ss.work_date=%s AND ss.is_work_day=1 "
    "AND (csa.status IS NULL OR csa.status<>'cancelled')"
)
_ASSIGNMENT_LOCK_SQL = f"{_ASSIGNMENT_QUERY_SQL} FOR UPDATE"
_EXISTING_COLUMNS = "id,case_no,assignment_id,staff_id,staff_line_user_id,service_date,baby_log_text,requires_cooking,content_fingerprint"
_EXISTING_SQL = f"SELECT {_EXISTING_COLUMNS} FROM scheduling_service_day_logs WHERE idempotency_key=%s FOR UPDATE"
_EXISTING_FOR_ASSIGNMENT_DAY_SQL = f"SELECT {_EXISTING_COLUMNS} FROM scheduling_service_day_logs WHERE assignment_id=%s AND service_date=%s FOR UPDATE"
_READBACK_SQL = f"SELECT {_EXISTING_COLUMNS} FROM scheduling_service_day_logs WHERE id=%s AND staff_id=%s AND staff_line_user_id=%s"
_ATTACHMENTS_READBACK_SQL = (
    "SELECT object.opaque_object_id AS controlled_file_object_id, "
    "staging.staging_id, object.content_sha256, attachment.attachment_kind, "
    "attachment.created_at_utc "
    "FROM scheduling_service_day_log_attachments attachment "
    "JOIN controlled_file_objects object "
    "ON object.id=attachment.controlled_file_object_id "
    "JOIN controlled_file_staging_objects staging "
    "ON staging.id=object.source_staging_id "
    "WHERE attachment.service_day_log_id=%s ORDER BY attachment.id"
)
_LOG_INSERT_SQL = (
    "INSERT INTO scheduling_service_day_logs (case_no,assignment_id,staff_id,staff_line_user_id,service_date,baby_log_text,requires_cooking,content_fingerprint,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_CONTROLLED_ATTACHMENT_INSERT_SQL = (
    "INSERT INTO scheduling_service_day_log_attachments "
    "(service_day_log_id,provider_media_id,controlled_file_object_id,attachment_kind) "
    "SELECT %s,NULL,object.id,%s FROM controlled_file_objects object "
    "JOIN controlled_file_staging_objects staging "
    "ON staging.id=object.source_staging_id "
    "WHERE object.opaque_object_id=%s AND staging.staging_id=%s "
    "AND object.object_key=%s AND object.content_sha256=%s "
    "AND object.owner_type='scheduling' AND object.purpose=%s"
)
_CANONICAL_SCHEDULING_OBJECT_SQL = (
    "SELECT object.object_key,object.content_sha256,object.owner_type,object.purpose "
    "FROM controlled_file_objects object "
    "JOIN controlled_file_staging_objects staging ON staging.id=object.source_staging_id "
    "WHERE object.opaque_object_id=%s AND staging.staging_id=%s "
    "FOR UPDATE"
)
_EVENT_INSERT_SQL = "INSERT INTO scheduling_service_day_log_events (service_day_log_id,assignment_id,staff_id,service_date,event_type,idempotency_key) VALUES (%s,%s,%s,%s,'submitted',%s)"
_OUTBOX_INSERT_SQL = "INSERT INTO scheduling_service_day_log_outbox (event_id,intent_key,payload_snapshot) VALUES (%s,%s,%s)"


__all__ = ["MySqlServiceDayLogRepository"]
