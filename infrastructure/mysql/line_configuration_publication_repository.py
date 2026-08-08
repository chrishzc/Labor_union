"""MySQL adapters for versioned LINE configuration and Rich Menu publications."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from pymysql.err import IntegrityError

from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationSnapshot,
)
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.identities import (
    LineConfigurationRevision,
    LineRichMenuPublicationId,
)
from domains.line.rich_menu import (
    LineRichMenuPublicationSnapshot,
    LineRichMenuPublicationStatus,
)
from infrastructure.mysql.line_repository_support import (
    aware_utc,
    canonical_json_value,
    database_utc,
    mysql_error_code,
    optional_row,
)
from shared_kernel.identities import CorrelationId
from subsystems.line.configuration_contracts import (
    ApplyLineConfigurationCommand,
    ApplyLineConfigurationResult,
    LineConfigurationCommandOutcome,
)
from subsystems.line.rich_menu_contracts import (
    ClaimLineRichMenuPublicationsQuery,
    LineRichMenuCommandOutcome,
    LineRichMenuPublicationQuery,
    LineRichMenuPublicationWorkItem,
    LineRichMenuProviderOutcomeType,
    QueueLineRichMenuPublicationCommand,
    QueueLineRichMenuPublicationResult,
    RecordLineRichMenuPublicationCommand,
    RetryLineRichMenuPublicationCommand,
)


class MySqlLineConfigurationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, kind: LineConfigurationKind) -> LineConfigurationSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(_CONFIG_SELECT_SQL, (kind.value,))
            row = optional_row(cursor.fetchone())
        if row is None:
            return LineConfigurationSnapshot(kind, LineConfigurationRevision(0), "{}")
        return _configuration_snapshot(row)

    def apply(
        self,
        command: ApplyLineConfigurationCommand,
    ) -> ApplyLineConfigurationResult:
        with self._connection.cursor() as cursor:
            existing = self._existing_revision(cursor, command)
            if existing is not None:
                return self._existing_result(existing, command)
            self._require_current_revision(cursor, command)
            revision_id = self._insert_revision(cursor, command)
            self._move_current(cursor, command, revision_id)
        return ApplyLineConfigurationResult(
            LineConfigurationCommandOutcome.CREATED,
            LineConfigurationSnapshot(
                command.candidate.kind,
                command.candidate.resulting_revision,
                command.candidate.definition_json,
            ),
        )

    def _existing_revision(self, cursor, command):
        cursor.execute(_CONFIG_BY_KEY_SQL, (command.idempotency_key.value,))
        return optional_row(cursor.fetchone())

    def _existing_result(self, row, command):
        candidate = command.candidate
        actual = (
            str(row["configuration_kind"]),
            int(row["revision"]),
            str(row["definition_fingerprint"]),
        )
        expected = (
            candidate.kind.value,
            candidate.resulting_revision.value,
            candidate.fingerprint.value,
        )
        if actual != expected:
            raise RuntimeError("line_configuration_idempotency_conflict")
        return ApplyLineConfigurationResult(
            LineConfigurationCommandOutcome.EXISTING,
            _configuration_snapshot(row),
        )

    def _require_current_revision(self, cursor, command):
        cursor.execute(_CONFIG_CURRENT_LOCK_SQL, (command.candidate.kind.value,))
        row = optional_row(cursor.fetchone())
        current_revision = 0 if row is None else int(row["revision"])
        if current_revision != command.candidate.before_revision.value:
            raise RuntimeError("line_configuration_revision_conflict")

    def _insert_revision(self, cursor, command):
        candidate = command.candidate
        cursor.execute(
            _CONFIG_INSERT_SQL,
            (
                candidate.kind.value,
                candidate.resulting_revision.value,
                candidate.definition_json,
                candidate.fingerprint.value,
                command.actor.actor_id,
                command.reason,
                command.idempotency_key.value,
                command.correlation_id.value,
            ),
        )
        return int(cursor.lastrowid)

    def _move_current(self, cursor, command, revision_id):
        candidate = command.candidate
        cursor.execute(
            _CONFIG_CURRENT_UPSERT_SQL,
            (candidate.kind.value, candidate.resulting_revision.value, revision_id),
        )


class MySqlLineRichMenuPublicationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(
        self,
        publication_id: LineRichMenuPublicationId,
    ) -> LineRichMenuPublicationSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_MENU_SELECT_SQL, (publication_id.value,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _publication_snapshot(row)

    def list(
        self,
        query: LineRichMenuPublicationQuery,
    ) -> tuple[LineRichMenuPublicationSnapshot, ...]:
        sql, parameters = _menu_list_statement(query)
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            rows = tuple(cursor.fetchall() or ())
        return tuple(_publication_snapshot(row) for row in rows)

    def queue(
        self,
        command: QueueLineRichMenuPublicationCommand,
    ) -> QueueLineRichMenuPublicationResult:
        try:
            publication_id = self._insert(command)
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            return self._existing_queue(command)
        created = LineRichMenuPublicationSnapshot(
            LineRichMenuPublicationId(publication_id),
            command.menu_definition_id,
            command.configuration_revision,
            LineRichMenuPublicationStatus.QUEUED,
        )
        return QueueLineRichMenuPublicationResult(LineRichMenuCommandOutcome.CREATED, created)

    def claim(
        self,
        query: ClaimLineRichMenuPublicationsQuery,
    ) -> tuple[LineRichMenuPublicationWorkItem, ...]:
        lease_expires_at = query.now + timedelta(seconds=90)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _MENU_CLAIM_SQL,
                (
                    database_utc(query.now),
                    database_utc(query.now),
                    database_utc(query.now),
                    query.batch_size,
                ),
            )
            rows = tuple(cursor.fetchall() or ())
            identifiers = tuple(int(row["id"]) for row in rows)
            for publication_id in identifiers:
                cursor.execute(
                    _MENU_CLAIM_UPDATE_SQL,
                    (
                        query.lease_owner,
                        database_utc(lease_expires_at),
                        publication_id,
                    ),
                )
            claimed = []
            for publication_id in identifiers:
                cursor.execute(_MENU_WORK_SELECT_SQL, (publication_id,))
                row = optional_row(cursor.fetchone())
                if row is not None:
                    claimed.append(_publication_work_item(row))
        return tuple(claimed)

    def record(self, command: RecordLineRichMenuPublicationCommand):
        item = command.work_item
        outcome = command.provider_outcome
        attempts = item.attempt_count + 1
        success = outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS
        retryable = outcome.outcome_type in {
            LineRichMenuProviderOutcomeType.RATE_LIMITED,
            LineRichMenuProviderOutcomeType.UNAVAILABLE,
            LineRichMenuProviderOutcomeType.TIMEOUT,
        }
        if success:
            status = LineRichMenuPublicationStatus.PUBLISHED
            next_attempt_at = None
        elif retryable and attempts < item.maximum_attempts:
            status = LineRichMenuPublicationStatus.PUBLISH_RETRYABLE_FAILED
            next_attempt_at = command.completed_at + timedelta(
                seconds=min(30 * (2 ** (attempts - 1)), 300)
            )
        else:
            status = LineRichMenuPublicationStatus.FAILED
            next_attempt_at = None
        with self._connection.cursor() as cursor:
            cursor.execute(
                _MENU_RECORD_SQL,
                (
                    status.value,
                    command.image_object_reference,
                    outcome.provider_menu_id if success else None,
                    attempts,
                    database_utc(next_attempt_at) if next_attempt_at else None,
                    outcome.error_code,
                    outcome.error_message,
                    item.publication.publication_id.value,
                    item.lease_owner,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_rich_menu_publication_lease_lost")
            if success:
                self._append_success_steps(cursor, command)
            cursor.execute(
                _MENU_SELECT_SQL,
                (item.publication.publication_id.value,),
            )
            row = cursor.fetchone()
        return _publication_snapshot(row)

    def _append_success_steps(self, cursor, command):
        item = command.work_item
        steps = ["create", "upload"]
        if json.loads(item.definition_json).get("set_as_default") is True:
            steps.append("switch")
        for step in steps:
            cursor.execute(
                _MENU_STEP_INSERT_SQL,
                (
                    item.publication.publication_id.value,
                    step,
                    command.provider_outcome.provider_menu_id,
                    f"rich-menu-step:{item.publication.publication_id.value}:{step}",
                    database_utc(command.completed_at),
                ),
            )

    def next_due_at(self):
        with self._connection.cursor() as cursor:
            cursor.execute(_MENU_NEXT_DUE_SQL)
            row = optional_row(cursor.fetchone())
        value = None if row is None else row.get("next_due_at_utc")
        return None if value is None else aware_utc(value)

    def retry(
        self,
        command: RetryLineRichMenuPublicationCommand,
    ) -> LineRichMenuPublicationSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(_MENU_WORK_SELECT_SQL + " FOR UPDATE", (command.publication_id.value,))
            row = optional_row(cursor.fetchone())
            if row is None:
                raise LookupError("line_rich_menu_publication_not_found")
            status = LineRichMenuPublicationStatus(str(row["publication_status"]))
            if status not in {
                LineRichMenuPublicationStatus.FAILED,
                LineRichMenuPublicationStatus.PUBLISH_RETRYABLE_FAILED,
            }:
                raise RuntimeError("line_rich_menu_retry_state_conflict")
            cursor.execute(_MENU_RETRY_SQL, (command.publication_id.value,))
            cursor.execute(_MENU_SELECT_SQL, (command.publication_id.value,))
            updated = cursor.fetchone()
        return _publication_snapshot(updated)

    def _insert(self, command):
        with self._connection.cursor() as cursor:
            definition_snapshot = self._definition_snapshot(cursor, command)
            cursor.execute(
                _MENU_INSERT_SQL,
                (
                    command.menu_definition_id,
                    command.configuration_revision.value,
                    LineRichMenuPublicationStatus.QUEUED.value,
                    definition_snapshot,
                    command.idempotency_key.value,
                    command.correlation_id.value,
                    command.actor.actor_id,
                ),
            )
            return int(cursor.lastrowid)

    def _definition_snapshot(self, cursor, command):
        cursor.execute(
            _MENU_CONFIGURATION_SELECT_SQL,
            (command.configuration_revision.value,),
        )
        row = optional_row(cursor.fetchone())
        if row is None:
            raise LookupError("line_rich_menu_configuration_revision_not_found")
        configuration = json.loads(canonical_json_value(row["definition_snapshot"]))
        menu = next(
            (
                item
                for item in configuration.get("menus", [])
                if isinstance(item, dict) and item.get("id") == command.menu_definition_id
            ),
            None,
        )
        if menu is None:
            raise LookupError("line_rich_menu_definition_not_found")
        return canonical_line_payload_json(menu)

    def _existing_queue(self, command):
        with self._connection.cursor() as cursor:
            cursor.execute(_MENU_SELECT_BY_KEY_SQL, (command.idempotency_key.value,))
            row = optional_row(cursor.fetchone())
        if row is None:
            raise RuntimeError("line_rich_menu_duplicate_missing")
        existing = _publication_snapshot(row)
        expected = (
            command.menu_definition_id,
            command.configuration_revision,
            LineRichMenuPublicationStatus.QUEUED,
        )
        actual = (
            existing.menu_definition_id,
            existing.configuration_revision,
            existing.status,
        )
        if actual != expected:
            raise RuntimeError("line_rich_menu_idempotency_conflict")
        return QueueLineRichMenuPublicationResult(LineRichMenuCommandOutcome.EXISTING, existing)


def _configuration_snapshot(row):
    return LineConfigurationSnapshot(
        LineConfigurationKind(str(row["configuration_kind"])),
        LineConfigurationRevision(int(row["revision"])),
        canonical_json_value(row["definition_snapshot"]),
    )


def _publication_snapshot(row):
    return LineRichMenuPublicationSnapshot(
        LineRichMenuPublicationId(int(row["id"])),
        str(row["menu_definition_id"]),
        LineConfigurationRevision(int(row["configuration_revision"])),
        LineRichMenuPublicationStatus(str(row["publication_status"])),
    )


def _publication_work_item(row):
    snapshot = _publication_snapshot(row)
    return LineRichMenuPublicationWorkItem(
        snapshot,
        canonical_json_value(row["definition_snapshot"]),
        str(row["image_object_reference"])
        if row.get("image_object_reference") is not None
        else None,
        int(row["attempt_count"]),
        int(row["max_attempts"]),
        str(row["lease_owner"]),
        aware_utc(row["lease_expires_at_utc"]),
        CorrelationId(str(row["correlation_id"])),
    )


def _menu_list_statement(query):
    parameters: list[object] = []
    where = ""
    if query.statuses:
        where = " WHERE publication_status IN (" + ",".join(["%s"] * len(query.statuses)) + ")"
        parameters.extend(item.value for item in query.statuses)
    parameters.append(query.page_size)
    return _MENU_LIST_SQL + where + " ORDER BY id DESC LIMIT %s", tuple(parameters)


_CONFIG_SELECT_SQL = (
    "SELECT current.configuration_kind,current.revision,revision.definition_snapshot "
    "FROM line_configuration_current AS current JOIN line_configuration_revisions AS revision "
    "ON revision.id=current.revision_id WHERE current.configuration_kind=%s"
)
_CONFIG_BY_KEY_SQL = (
    "SELECT configuration_kind,revision,definition_snapshot,definition_fingerprint "
    "FROM line_configuration_revisions WHERE idempotency_key=%s"
)
_CONFIG_CURRENT_LOCK_SQL = (
    "SELECT revision FROM line_configuration_current WHERE configuration_kind=%s FOR UPDATE"
)
_CONFIG_INSERT_SQL = (
    "INSERT INTO line_configuration_revisions (configuration_kind,revision,"
    "definition_snapshot,definition_fingerprint,actor_id,reason,idempotency_key,"
    "correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
)
_CONFIG_CURRENT_UPSERT_SQL = (
    "INSERT INTO line_configuration_current (configuration_kind,revision,revision_id) "
    "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE revision=VALUES(revision),"
    "revision_id=VALUES(revision_id)"
)
_MENU_COLUMNS = (
    "id,menu_definition_id,configuration_revision,publication_status"
)
_MENU_SELECT_SQL = (
    f"SELECT {_MENU_COLUMNS} FROM line_rich_menu_publication_tasks WHERE id=%s"
)
_MENU_SELECT_BY_KEY_SQL = (
    f"SELECT {_MENU_COLUMNS} FROM line_rich_menu_publication_tasks WHERE idempotency_key=%s"
)
_MENU_WORK_COLUMNS = (
    _MENU_COLUMNS
    + ",definition_snapshot,image_object_reference,attempt_count,max_attempts,"
    "lease_owner,lease_expires_at_utc,correlation_id"
)
_MENU_WORK_SELECT_SQL = (
    f"SELECT {_MENU_WORK_COLUMNS} FROM line_rich_menu_publication_tasks WHERE id=%s"
)
_MENU_CLAIM_SQL = (
    f"SELECT {_MENU_WORK_COLUMNS} FROM line_rich_menu_publication_tasks WHERE "
    "((publication_status='queued' AND (next_attempt_at_utc IS NULL OR next_attempt_at_utc<=%s)) "
    "OR (publication_status='publish_retryable_failed' AND next_attempt_at_utc<=%s) "
    "OR (publication_status='publishing' AND lease_expires_at_utc<=%s)) "
    "ORDER BY COALESCE(next_attempt_at_utc,created_at_utc),id LIMIT %s "
    "FOR UPDATE SKIP LOCKED"
)
_MENU_CLAIM_UPDATE_SQL = (
    "UPDATE line_rich_menu_publication_tasks SET publication_status='publishing',"
    "lease_owner=%s,lease_expires_at_utc=%s WHERE id=%s"
)
_MENU_RECORD_SQL = (
    "UPDATE line_rich_menu_publication_tasks SET publication_status=%s,"
    "image_object_reference=%s,provider_menu_id=%s,attempt_count=%s,"
    "next_attempt_at_utc=%s,error_code=%s,error_message=%s,lease_owner=NULL,"
    "lease_expires_at_utc=NULL WHERE id=%s AND lease_owner=%s "
    "AND publication_status='publishing'"
)
_MENU_STEP_INSERT_SQL = (
    "INSERT IGNORE INTO line_rich_menu_publication_step_receipts "
    "(publication_id,step_name,provider_menu_id,idempotency_key,completed_at_utc) "
    "VALUES (%s,%s,%s,%s,%s)"
)
_MENU_NEXT_DUE_SQL = (
    "SELECT MIN(CASE WHEN publication_status='queued' THEN "
    "COALESCE(next_attempt_at_utc,created_at_utc) "
    "WHEN publication_status='publish_retryable_failed' THEN next_attempt_at_utc "
    "WHEN publication_status='publishing' THEN lease_expires_at_utc END) AS next_due_at_utc "
    "FROM line_rich_menu_publication_tasks WHERE publication_status IN "
    "('queued','publish_retryable_failed','publishing')"
)
_MENU_RETRY_SQL = (
    "UPDATE line_rich_menu_publication_tasks SET publication_status='queued',"
    "attempt_count=0,next_attempt_at_utc=NULL,lease_owner=NULL,lease_expires_at_utc=NULL,"
    "error_code=NULL,error_message=NULL WHERE id=%s"
)
_MENU_LIST_SQL = f"SELECT {_MENU_COLUMNS} FROM line_rich_menu_publication_tasks"
_MENU_CONFIGURATION_SELECT_SQL = (
    "SELECT definition_snapshot FROM line_configuration_revisions "
    "WHERE configuration_kind='rich_menus' AND revision=%s"
)
_MENU_INSERT_SQL = (
    "INSERT INTO line_rich_menu_publication_tasks (menu_definition_id,"
    "configuration_revision,operation,publication_status,definition_snapshot,"
    "idempotency_key,correlation_id,requested_by_actor_id) "
    "VALUES (%s,%s,'publish',%s,%s,%s,%s,%s)"
)


__all__ = [
    "MySqlLineConfigurationRepository",
    "MySqlLineRichMenuPublicationRepository",
]
