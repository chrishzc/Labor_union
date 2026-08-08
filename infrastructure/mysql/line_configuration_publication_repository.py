"""MySQL adapters for versioned LINE configuration and Rich Menu publications."""

from __future__ import annotations

from typing import Any

from pymysql.err import IntegrityError

from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationSnapshot,
)
from domains.line.identities import (
    LineConfigurationRevision,
    LineRichMenuPublicationId,
)
from domains.line.rich_menu import (
    LineRichMenuPublicationSnapshot,
    LineRichMenuPublicationStatus,
)
from infrastructure.mysql.line_repository_support import (
    canonical_json_value,
    mysql_error_code,
    optional_row,
)
from subsystems.line.configuration_contracts import (
    ApplyLineConfigurationCommand,
    ApplyLineConfigurationResult,
    LineConfigurationCommandOutcome,
)
from subsystems.line.rich_menu_contracts import (
    LineRichMenuCommandOutcome,
    LineRichMenuPublicationQuery,
    QueueLineRichMenuPublicationResult,
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
        snapshot: LineRichMenuPublicationSnapshot,
        idempotency_key,
    ) -> QueueLineRichMenuPublicationResult:
        try:
            publication_id = self._insert(snapshot, idempotency_key.value)
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            return self._existing_queue(snapshot, idempotency_key.value)
        created = LineRichMenuPublicationSnapshot(
            LineRichMenuPublicationId(publication_id),
            snapshot.menu_definition_id,
            snapshot.configuration_revision,
            snapshot.status,
        )
        return QueueLineRichMenuPublicationResult(LineRichMenuCommandOutcome.CREATED, created)

    def _insert(self, snapshot, idempotency_key):
        with self._connection.cursor() as cursor:
            definition_snapshot = self._definition_snapshot(cursor, snapshot)
            cursor.execute(
                _MENU_INSERT_SQL,
                (
                    snapshot.menu_definition_id,
                    snapshot.configuration_revision.value,
                    snapshot.status.value,
                    definition_snapshot,
                    idempotency_key,
                    f"line-rich-menu:{idempotency_key}",
                ),
            )
            return int(cursor.lastrowid)

    def _definition_snapshot(self, cursor, snapshot):
        cursor.execute(
            _MENU_CONFIGURATION_SELECT_SQL,
            (snapshot.configuration_revision.value,),
        )
        row = optional_row(cursor.fetchone())
        if row is None:
            raise LookupError("line_rich_menu_configuration_revision_not_found")
        return canonical_json_value(row["definition_snapshot"])

    def _existing_queue(self, snapshot, idempotency_key):
        with self._connection.cursor() as cursor:
            cursor.execute(_MENU_SELECT_BY_KEY_SQL, (idempotency_key,))
            row = optional_row(cursor.fetchone())
        if row is None:
            raise RuntimeError("line_rich_menu_duplicate_missing")
        existing = _publication_snapshot(row)
        expected = (
            snapshot.menu_definition_id,
            snapshot.configuration_revision,
            snapshot.status,
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
_MENU_LIST_SQL = f"SELECT {_MENU_COLUMNS} FROM line_rich_menu_publication_tasks"
_MENU_CONFIGURATION_SELECT_SQL = (
    "SELECT definition_snapshot FROM line_configuration_revisions "
    "WHERE configuration_kind='rich_menus' AND revision=%s"
)
_MENU_INSERT_SQL = (
    "INSERT INTO line_rich_menu_publication_tasks (menu_definition_id,"
    "configuration_revision,operation,publication_status,definition_snapshot,"
    "idempotency_key,correlation_id,requested_by_actor_id) "
    "VALUES (%s,%s,'publish',%s,%s,%s,%s,'line-subsystem')"
)


__all__ = [
    "MySqlLineConfigurationRepository",
    "MySqlLineRichMenuPublicationRepository",
]
