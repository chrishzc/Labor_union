"""
File: line_configuration_publication_repository.py
Description: 保存 LINE Configuration、Rich Menu publication、cleanup-only claim 與不可變 step receipt。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timedelta
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
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.validation import require_nonnegative_integer
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
from subsystems.line.ports import (
    LineRichMenuCleanupAnomaly,
    LineRichMenuCleanupWorkItem,
    LineRichMenuPublicationPage,
    LineRichMenuPublicationStep,
    LineRichMenuStepAttemptEvent,
    LineRichMenuStepAttemptOutcome,
    LineRichMenuStepReceipt,
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

    def list_page(
        self,
        query: LineRichMenuPublicationQuery,
        *,
        offset: int = 0,
    ) -> LineRichMenuPublicationPage:
        require_nonnegative_integer(offset, "LINE Rich Menu publication offset")
        count_sql, count_parameters = _menu_count_statement(query)
        page_sql, page_parameters = _menu_page_statement(query, offset)
        with self._connection.cursor() as cursor:
            cursor.execute(count_sql, count_parameters)
            count_row = optional_row(cursor.fetchone())
            if count_row is None or isinstance(count_row.get("total"), bool):
                raise RuntimeError("line_rich_menu_publication_total_missing")
            total = count_row.get("total")
            require_nonnegative_integer(total, "LINE Rich Menu publication total")
            cursor.execute(page_sql, page_parameters)
            rows = tuple(cursor.fetchall() or ())
        items = tuple(_publication_snapshot(row) for row in rows)
        return LineRichMenuPublicationPage(items, total, offset, query.page_size)

    def published_provider_menu_id(self, menu_definition_id: str) -> str | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_MENU_PUBLISHED_PROVIDER_ID_SQL, (menu_definition_id, menu_definition_id))
            row = optional_row(cursor.fetchone())
        if row is None or not row.get("provider_menu_id"):
            return None
        return str(row["provider_menu_id"])

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
                    database_utc(query.now),
                    query.batch_size,
                ),
            )
            rows = tuple(cursor.fetchall() or ())
            identifiers = tuple(
                (int(row["id"]), str(row["publication_status"])) for row in rows
            )
            for publication_id, status in identifiers:
                if status == LineRichMenuPublicationStatus.PUBLISHED.value:
                    cursor.execute(
                        _MENU_CLEANUP_CLAIM_UPDATE_SQL,
                        (
                            query.lease_owner,
                            database_utc(lease_expires_at),
                            database_utc(query.now),
                            publication_id,
                        ),
                    )
                else:
                    cursor.execute(
                        _MENU_CLAIM_UPDATE_SQL,
                        (
                            query.lease_owner,
                            database_utc(lease_expires_at),
                            publication_id,
                        ),
                    )
                if cursor.rowcount != 1:
                    raise RuntimeError("line_rich_menu_publication_claim_lost")
            claimed = []
            for publication_id, _status in identifiers:
                cursor.execute(_MENU_WORK_SELECT_SQL, (publication_id,))
                row = optional_row(cursor.fetchone())
                if row is None:
                    raise RuntimeError("line_rich_menu_publication_claim_missing")
                claimed.append(_publication_work_item(row))
        return tuple(claimed)

    def persist_cleanup_target(
        self,
        publication_id: LineRichMenuPublicationId,
        lease_owner: str,
        provider_menu_id: str,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _MENU_PERSIST_CLEANUP_TARGET_SQL,
                (
                    provider_menu_id,
                    publication_id.value,
                    lease_owner,
                    provider_menu_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_rich_menu_cleanup_target_conflict")

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

    def list_step_receipts(
        self,
        publication_id: LineRichMenuPublicationId,
    ) -> tuple[LineRichMenuStepReceipt, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _MENU_STEP_RECEIPTS_SELECT_SQL,
                (publication_id.value,),
            )
            rows = tuple(cursor.fetchall() or ())
        return tuple(
            _step_receipt_from_row(row, publication_id=publication_id)
            for row in rows
        )

    def append_step_receipt(
        self,
        receipt: LineRichMenuStepReceipt,
    ) -> LineRichMenuStepReceipt:
        if receipt.provider_menu_id is None:
            raise ValueError("line_rich_menu_step_receipt_provider_id_required")
        parameters = (
            receipt.publication_id.value,
            receipt.step.value,
            receipt.request_fingerprint.value,
            receipt.idempotency_key.value,
            receipt.provider_menu_id,
            database_utc(receipt.acknowledged_at),
        )
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(_MENU_STEP_RECEIPT_INSERT_SQL, parameters)
                cursor.execute(
                    _MENU_STEP_RECEIPT_SELECT_BY_STEP_SQL,
                    (receipt.publication_id.value, receipt.step.value),
                )
                row = optional_row(cursor.fetchone())
                if row is None:
                    raise RuntimeError("line_rich_menu_step_receipt_missing")
                persisted = _step_receipt_from_row(
                    row,
                    publication_id=receipt.publication_id,
                )
                _require_same_step_receipt(persisted, receipt)
                return persisted
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            with self._connection.cursor() as cursor:
                cursor.execute(
                    _MENU_STEP_RECEIPT_SELECT_BY_STEP_SQL,
                    (receipt.publication_id.value, receipt.step.value),
                )
                by_step = optional_row(cursor.fetchone())
                cursor.execute(
                    _MENU_STEP_RECEIPT_SELECT_BY_KEY_SQL,
                    (receipt.idempotency_key.value,),
                )
                by_key = optional_row(cursor.fetchone())
            if by_step is None and by_key is None:
                raise RuntimeError("line_rich_menu_step_receipt_duplicate_missing")
            if by_step is None or by_key is None:
                raise RuntimeError("line_rich_menu_step_receipt_idempotency_conflict")
            persisted_by_step = _step_receipt_from_row(
                by_step,
                publication_id=receipt.publication_id,
            )
            persisted_by_key = _step_receipt_from_row(by_key)
            if persisted_by_step != persisted_by_key:
                raise RuntimeError("line_rich_menu_step_receipt_collision")
            _require_same_step_receipt(persisted_by_step, receipt)
            return persisted_by_step

    def list_step_attempt_events(
        self,
        publication_id: LineRichMenuPublicationId,
        step: LineRichMenuPublicationStep | None = None,
    ) -> tuple[LineRichMenuStepAttemptEvent, ...]:
        parameters: tuple[object, ...]
        if step is None:
            sql = _MENU_STEP_ATTEMPTS_SELECT_SQL
            parameters = (publication_id.value,)
        else:
            if not isinstance(step, LineRichMenuPublicationStep):
                raise TypeError("line_rich_menu_step_attempt_step_invalid")
            sql = _MENU_STEP_ATTEMPTS_SELECT_BY_STEP_SQL
            parameters = (publication_id.value, step.value)
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            rows = tuple(cursor.fetchall() or ())
        return tuple(
            _step_attempt_event_from_row(row, publication_id=publication_id)
            for row in rows
        )

    def append_step_attempt_event(
        self,
        event: LineRichMenuStepAttemptEvent,
    ) -> LineRichMenuStepAttemptEvent:
        parameters = (
            event.publication_id.value,
            event.step.value,
            event.attempt_number,
            event.request_fingerprint.value,
            event.idempotency_key.value,
            event.outcome.value,
            event.provider_menu_id,
            event.error_code,
            database_utc(event.attempted_at),
            event.correlation_id.value,
        )
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(_MENU_STEP_ATTEMPT_INSERT_SQL, parameters)
                cursor.execute(
                    _MENU_STEP_ATTEMPT_SELECT_BY_ATTEMPT_SQL,
                    (
                        event.publication_id.value,
                        event.step.value,
                        event.attempt_number,
                    ),
                )
                row = optional_row(cursor.fetchone())
                if row is None:
                    raise RuntimeError("line_rich_menu_step_attempt_missing")
                persisted = _step_attempt_event_from_row(
                    row,
                    publication_id=event.publication_id,
                )
                _require_same_step_attempt(persisted, event)
                return persisted
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            with self._connection.cursor() as cursor:
                cursor.execute(
                    _MENU_STEP_ATTEMPT_SELECT_BY_ATTEMPT_SQL,
                    (
                        event.publication_id.value,
                        event.step.value,
                        event.attempt_number,
                    ),
                )
                by_attempt = optional_row(cursor.fetchone())
                cursor.execute(
                    _MENU_STEP_ATTEMPT_SELECT_BY_KEY_SQL,
                    (event.idempotency_key.value,),
                )
                by_key = optional_row(cursor.fetchone())
            if by_attempt is None and by_key is None:
                raise RuntimeError("line_rich_menu_step_attempt_duplicate_missing")
            if by_attempt is None or by_key is None:
                raise RuntimeError("line_rich_menu_step_attempt_idempotency_conflict")
            persisted_by_attempt = _step_attempt_event_from_row(
                by_attempt,
                publication_id=event.publication_id,
            )
            persisted_by_key = _step_attempt_event_from_row(by_key)
            if persisted_by_attempt != persisted_by_key:
                raise RuntimeError("line_rich_menu_step_attempt_collision")
            _require_same_step_attempt(persisted_by_attempt, event)
            return persisted_by_attempt

    def append_cleanup_anomaly(
        self,
        anomaly: LineRichMenuCleanupAnomaly,
    ) -> None:
        fingerprint, idempotency_key, occurred_at = _cleanup_anomaly_identity(anomaly)
        parameters = (
            anomaly.publication_id.value,
            fingerprint,
            idempotency_key,
            anomaly.error_code,
            database_utc(occurred_at),
        )
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(_MENU_CLEANUP_ANOMALY_INSERT_SQL, parameters)
                cursor.execute(
                    _MENU_CLEANUP_ANOMALY_SELECT_BY_KEY_SQL,
                    (idempotency_key,),
                )
                row = optional_row(cursor.fetchone())
                if row is None:
                    raise RuntimeError("line_rich_menu_cleanup_anomaly_missing")
                persisted = _cleanup_anomaly_from_row(row)
                _require_same_cleanup_anomaly(
                    persisted,
                    anomaly,
                    fingerprint=fingerprint,
                    idempotency_key=idempotency_key,
                    occurred_at=occurred_at,
                )
                return None
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            with self._connection.cursor() as cursor:
                cursor.execute(
                    _MENU_CLEANUP_ANOMALY_SELECT_BY_KEY_SQL,
                    (idempotency_key,),
                )
                row = optional_row(cursor.fetchone())
            if row is None:
                raise RuntimeError("line_rich_menu_cleanup_anomaly_duplicate_missing")
            persisted = _cleanup_anomaly_from_row(row)
            _require_same_cleanup_anomaly(
                persisted,
                anomaly,
                fingerprint=fingerprint,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
            )
            return None

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
            publication_id = int(cursor.lastrowid)
            return publication_id

    def _lock_preview(self, cursor, command):
        """Legacy preview-table helper; canonical stateless Apply never calls it."""
        cursor.execute(
            _MENU_PREVIEW_LOCK_SQL,
            (
                command.preview_id,
                command.menu_definition_id,
                command.preview_config_revision,
                command.preview_config_fingerprint,
                command.previewed_by_admin_user_id,
            ),
        )
        if optional_row(cursor.fetchone()) is None:
            raise RuntimeError("line_rich_menu_current_preview_required")

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
    values = (
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
    if snapshot.status is not LineRichMenuPublicationStatus.PUBLISHED:
        return LineRichMenuPublicationWorkItem(*values)
    provider_menu_id = row.get("provider_menu_id")
    if not isinstance(provider_menu_id, str):
        raise ValueError("line_rich_menu_cleanup_provider_menu_id_missing")
    previous_provider_menu_id = row.get("previous_provider_menu_id")
    if previous_provider_menu_id is not None and not isinstance(
        previous_provider_menu_id,
        str,
    ):
        raise ValueError("line_rich_menu_cleanup_previous_provider_menu_id_invalid")
    return LineRichMenuCleanupWorkItem(
        *values,
        provider_menu_id,
        previous_provider_menu_id,
    )


def _menu_list_statement(query):
    where, parameters = _menu_query_filter(query)
    parameters.append(query.page_size)
    return _MENU_LIST_SQL + where + " ORDER BY id DESC LIMIT %s", tuple(parameters)


def _menu_count_statement(query):
    where, parameters = _menu_query_filter(query)
    return _MENU_COUNT_SQL + where, tuple(parameters)


def _menu_page_statement(query, offset: int):
    where, parameters = _menu_query_filter(query)
    parameters.extend((query.page_size, offset))
    return _MENU_LIST_SQL + where + " ORDER BY id DESC LIMIT %s OFFSET %s", tuple(parameters)


def _menu_query_filter(query):
    parameters: list[object] = []
    predicates: list[str] = []
    if query.menu_definition_id is not None:
        predicates.append("menu_definition_id=%s")
        parameters.append(query.menu_definition_id)
    if query.statuses:
        predicates.append(
            "publication_status IN ("
            + ",".join(["%s"] * len(query.statuses))
            + ")"
        )
        parameters.extend(item.value for item in query.statuses)
    where = "" if not predicates else " WHERE " + " AND ".join(predicates)
    return where, parameters


_STEP_RECEIPT_ROW_KEYS = frozenset(
    {
        "publication_id",
        "step_name",
        "request_fingerprint",
        "idempotency_key",
        "provider_menu_id",
        "acknowledged_at_utc",
    }
)
_CLEANUP_ANOMALY_ROW_KEYS = frozenset(
    {
        "publication_id",
        "request_fingerprint",
        "idempotency_key",
        "error_code",
        "occurred_at_utc",
    }
)


def _step_receipt_from_row(
    row: object,
    *,
    publication_id: LineRichMenuPublicationId | None = None,
) -> LineRichMenuStepReceipt:
    if not isinstance(row, Mapping) or frozenset(row) != _STEP_RECEIPT_ROW_KEYS:
        raise ValueError("line_rich_menu_step_receipt_row_shape_invalid")
    persisted_publication_id = row["publication_id"]
    if (
        isinstance(persisted_publication_id, bool)
        or not isinstance(persisted_publication_id, int)
        or persisted_publication_id <= 0
    ):
        raise ValueError("line_rich_menu_step_receipt_publication_id_invalid")
    typed_publication_id = LineRichMenuPublicationId(persisted_publication_id)
    if publication_id is not None and typed_publication_id != publication_id:
        raise ValueError("line_rich_menu_step_receipt_publication_id_mismatch")
    step_value = row["step_name"]
    if not isinstance(step_value, str):
        raise ValueError("line_rich_menu_step_receipt_step_invalid")
    try:
        step = LineRichMenuPublicationStep(step_value)
    except ValueError as error:
        raise ValueError("line_rich_menu_step_receipt_step_invalid") from error
    fingerprint_value = row["request_fingerprint"]
    if not isinstance(fingerprint_value, str):
        raise ValueError("line_rich_menu_step_receipt_fingerprint_invalid")
    idempotency_value = row["idempotency_key"]
    if not isinstance(idempotency_value, str):
        raise ValueError("line_rich_menu_step_receipt_idempotency_key_invalid")
    provider_menu_id = row["provider_menu_id"]
    if not isinstance(provider_menu_id, str):
        raise ValueError("line_rich_menu_step_receipt_provider_id_invalid")
    acknowledged_at = row["acknowledged_at_utc"]
    if not isinstance(acknowledged_at, datetime):
        raise ValueError("line_rich_menu_step_receipt_time_invalid")
    try:
        return LineRichMenuStepReceipt(
            typed_publication_id,
            step,
            PreviewFingerprint(fingerprint_value),
            IdempotencyKey(idempotency_value),
            aware_utc(acknowledged_at),
            provider_menu_id,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("line_rich_menu_step_receipt_row_invalid") from error


def _require_same_step_receipt(
    persisted: LineRichMenuStepReceipt,
    expected: LineRichMenuStepReceipt,
) -> None:
    if (
        persisted.publication_id != expected.publication_id
        or persisted.step is not expected.step
        or persisted.request_fingerprint != expected.request_fingerprint
        or persisted.idempotency_key != expected.idempotency_key
        or persisted.provider_menu_id != expected.provider_menu_id
        or persisted.acknowledged_at != aware_utc(expected.acknowledged_at)
    ):
        raise RuntimeError("line_rich_menu_step_receipt_idempotency_conflict")


_STEP_ATTEMPT_ROW_KEYS = frozenset(
    {
        "publication_id",
        "step_name",
        "attempt_number",
        "request_fingerprint",
        "idempotency_key",
        "outcome",
        "provider_menu_id",
        "error_code",
        "attempted_at_utc",
        "correlation_id",
    }
)


def _step_attempt_event_from_row(
    row: object,
    *,
    publication_id: LineRichMenuPublicationId | None = None,
) -> LineRichMenuStepAttemptEvent:
    if not isinstance(row, Mapping) or frozenset(row) != _STEP_ATTEMPT_ROW_KEYS:
        raise ValueError("line_rich_menu_step_attempt_row_shape_invalid")
    persisted_publication_id = row["publication_id"]
    if (
        isinstance(persisted_publication_id, bool)
        or not isinstance(persisted_publication_id, int)
        or persisted_publication_id <= 0
    ):
        raise ValueError("line_rich_menu_step_attempt_publication_id_invalid")
    typed_publication_id = LineRichMenuPublicationId(persisted_publication_id)
    if publication_id is not None and typed_publication_id != publication_id:
        raise ValueError("line_rich_menu_step_attempt_publication_id_mismatch")
    step_value = row["step_name"]
    if not isinstance(step_value, str):
        raise ValueError("line_rich_menu_step_attempt_step_invalid")
    try:
        step = LineRichMenuPublicationStep(step_value)
    except ValueError as error:
        raise ValueError("line_rich_menu_step_attempt_step_invalid") from error
    attempt_number = row["attempt_number"]
    if (
        isinstance(attempt_number, bool)
        or not isinstance(attempt_number, int)
        or attempt_number <= 0
    ):
        raise ValueError("line_rich_menu_step_attempt_number_invalid")
    fingerprint_value = row["request_fingerprint"]
    idempotency_value = row["idempotency_key"]
    outcome_value = row["outcome"]
    attempted_at = row["attempted_at_utc"]
    correlation_value = row["correlation_id"]
    if not isinstance(fingerprint_value, str):
        raise ValueError("line_rich_menu_step_attempt_fingerprint_invalid")
    if not isinstance(idempotency_value, str):
        raise ValueError("line_rich_menu_step_attempt_idempotency_key_invalid")
    if not isinstance(outcome_value, str):
        raise ValueError("line_rich_menu_step_attempt_outcome_invalid")
    try:
        outcome = LineRichMenuStepAttemptOutcome(outcome_value)
    except ValueError as error:
        raise ValueError("line_rich_menu_step_attempt_outcome_invalid") from error
    provider_menu_id = row["provider_menu_id"]
    error_code = row["error_code"]
    if provider_menu_id is not None and not isinstance(provider_menu_id, str):
        raise ValueError("line_rich_menu_step_attempt_provider_id_invalid")
    if error_code is not None and not isinstance(error_code, str):
        raise ValueError("line_rich_menu_step_attempt_error_code_invalid")
    if not isinstance(attempted_at, datetime):
        raise ValueError("line_rich_menu_step_attempt_time_invalid")
    if not isinstance(correlation_value, str):
        raise ValueError("line_rich_menu_step_attempt_correlation_id_invalid")
    try:
        return LineRichMenuStepAttemptEvent(
            typed_publication_id,
            step,
            attempt_number,
            PreviewFingerprint(fingerprint_value),
            IdempotencyKey(idempotency_value),
            outcome,
            aware_utc(attempted_at),
            CorrelationId(correlation_value),
            provider_menu_id,
            error_code,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("line_rich_menu_step_attempt_row_invalid") from error


def _require_same_step_attempt(
    persisted: LineRichMenuStepAttemptEvent,
    expected: LineRichMenuStepAttemptEvent,
) -> None:
    if (
        persisted.publication_id != expected.publication_id
        or persisted.step is not expected.step
        or persisted.attempt_number != expected.attempt_number
        or persisted.request_fingerprint != expected.request_fingerprint
        or persisted.idempotency_key != expected.idempotency_key
        or persisted.outcome is not expected.outcome
        or persisted.attempted_at != aware_utc(expected.attempted_at)
        or persisted.correlation_id != expected.correlation_id
        or persisted.provider_menu_id != expected.provider_menu_id
        or persisted.error_code != expected.error_code
    ):
        raise RuntimeError("line_rich_menu_step_attempt_idempotency_conflict")


def _cleanup_anomaly_identity(
    anomaly: LineRichMenuCleanupAnomaly,
) -> tuple[str, str, datetime]:
    occurred_at = aware_utc(anomaly.occurred_at)
    occurred_at_text = occurred_at.isoformat(timespec="microseconds")
    fingerprint = fingerprint_payload(
        {
            "publication_id": anomaly.publication_id.value,
            "error_code": anomaly.error_code,
            "occurred_at_utc": occurred_at_text,
        }
    ).value
    return (
        fingerprint,
        f"line-rich-menu-cleanup:{anomaly.publication_id.value}:{fingerprint}",
        occurred_at,
    )


def _cleanup_anomaly_from_row(
    row: object,
) -> tuple[LineRichMenuCleanupAnomaly, PreviewFingerprint, IdempotencyKey]:
    if not isinstance(row, Mapping) or frozenset(row) != _CLEANUP_ANOMALY_ROW_KEYS:
        raise ValueError("line_rich_menu_cleanup_anomaly_row_shape_invalid")
    publication_id = row["publication_id"]
    if (
        isinstance(publication_id, bool)
        or not isinstance(publication_id, int)
        or publication_id <= 0
    ):
        raise ValueError("line_rich_menu_cleanup_anomaly_publication_id_invalid")
    fingerprint_value = row["request_fingerprint"]
    idempotency_value = row["idempotency_key"]
    error_code = row["error_code"]
    occurred_at = row["occurred_at_utc"]
    if not isinstance(fingerprint_value, str):
        raise ValueError("line_rich_menu_cleanup_anomaly_fingerprint_invalid")
    if not isinstance(idempotency_value, str):
        raise ValueError("line_rich_menu_cleanup_anomaly_idempotency_key_invalid")
    if not isinstance(error_code, str):
        raise ValueError("line_rich_menu_cleanup_anomaly_error_code_invalid")
    if not isinstance(occurred_at, datetime):
        raise ValueError("line_rich_menu_cleanup_anomaly_time_invalid")
    try:
        fingerprint = PreviewFingerprint(fingerprint_value)
        idempotency_key = IdempotencyKey(idempotency_value)
        anomaly = LineRichMenuCleanupAnomaly(
            LineRichMenuPublicationId(publication_id),
            error_code,
            aware_utc(occurred_at),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("line_rich_menu_cleanup_anomaly_row_invalid") from error
    return anomaly, fingerprint, idempotency_key


def _require_same_cleanup_anomaly(
    persisted: tuple[LineRichMenuCleanupAnomaly, PreviewFingerprint, IdempotencyKey],
    expected: LineRichMenuCleanupAnomaly,
    *,
    fingerprint: str,
    idempotency_key: str,
    occurred_at: datetime,
) -> None:
    persisted_anomaly, persisted_fingerprint, persisted_key = persisted
    if (
        persisted_anomaly.publication_id != expected.publication_id
        or persisted_anomaly.error_code != expected.error_code
        or persisted_anomaly.occurred_at != occurred_at
        or persisted_fingerprint.value != fingerprint
        or persisted_key.value != idempotency_key
    ):
        raise RuntimeError("line_rich_menu_cleanup_anomaly_idempotency_conflict")


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
    "lease_owner,lease_expires_at_utc,correlation_id,provider_menu_id,"
    "previous_provider_menu_id"
)
_MENU_WORK_SELECT_SQL = (
    f"SELECT {_MENU_WORK_COLUMNS} FROM line_rich_menu_publication_tasks WHERE id=%s"
)
_MENU_CLAIM_SQL = (
    f"SELECT {_MENU_WORK_COLUMNS} FROM line_rich_menu_publication_tasks WHERE "
    "((publication_status='queued' AND (next_attempt_at_utc IS NULL OR next_attempt_at_utc<=%s)) "
    "OR (publication_status='publish_retryable_failed' AND next_attempt_at_utc<=%s) "
    "OR (publication_status='publishing' AND lease_expires_at_utc<=%s) "
    "OR (publication_status='published' "
    "AND (lease_owner IS NULL OR lease_expires_at_utc<=%s) "
    "AND NOT EXISTS (SELECT 1 FROM line_rich_menu_publication_step_acknowledgements "
    "AS cleanup_ack WHERE cleanup_ack.publication_id="
    "line_rich_menu_publication_tasks.id AND cleanup_ack.step_name='cleanup'))) "
    "ORDER BY COALESCE(next_attempt_at_utc,created_at_utc),id LIMIT %s "
    "FOR UPDATE SKIP LOCKED"
)
_MENU_CLAIM_UPDATE_SQL = (
    "UPDATE line_rich_menu_publication_tasks SET publication_status='publishing',"
    "lease_owner=%s,lease_expires_at_utc=%s WHERE id=%s"
)
_MENU_CLEANUP_CLAIM_UPDATE_SQL = (
    "UPDATE line_rich_menu_publication_tasks SET lease_owner=%s,"
    "lease_expires_at_utc=%s WHERE publication_status='published' "
    "AND (lease_owner IS NULL OR lease_expires_at_utc<=%s) AND id=%s "
    "AND NOT EXISTS (SELECT 1 FROM "
    "line_rich_menu_publication_step_acknowledgements AS cleanup_ack "
    "WHERE cleanup_ack.publication_id=line_rich_menu_publication_tasks.id "
    "AND cleanup_ack.step_name='cleanup')"
)
_MENU_PERSIST_CLEANUP_TARGET_SQL = (
    "UPDATE line_rich_menu_publication_tasks SET previous_provider_menu_id=%s "
    "WHERE id=%s AND lease_owner=%s AND publication_status='publishing' "
    "AND (previous_provider_menu_id IS NULL OR previous_provider_menu_id=%s)"
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
_MENU_STEP_RECEIPT_COLUMNS = (
    "publication_id,step_name,request_fingerprint,idempotency_key,"
    "provider_menu_id,acknowledged_at_utc"
)
_MENU_STEP_RECEIPTS_SELECT_SQL = (
    f"SELECT {_MENU_STEP_RECEIPT_COLUMNS} "
    "FROM line_rich_menu_publication_step_acknowledgements "
    "WHERE publication_id=%s ORDER BY id ASC"
)
_MENU_STEP_RECEIPT_SELECT_BY_STEP_SQL = (
    f"SELECT {_MENU_STEP_RECEIPT_COLUMNS} "
    "FROM line_rich_menu_publication_step_acknowledgements "
    "WHERE publication_id=%s AND step_name=%s"
)
_MENU_STEP_RECEIPT_SELECT_BY_KEY_SQL = (
    f"SELECT {_MENU_STEP_RECEIPT_COLUMNS} "
    "FROM line_rich_menu_publication_step_acknowledgements "
    "WHERE idempotency_key=%s"
)
_MENU_STEP_RECEIPT_INSERT_SQL = (
    "INSERT INTO line_rich_menu_publication_step_acknowledgements "
    "(publication_id,step_name,request_fingerprint,idempotency_key,"
    "provider_menu_id,acknowledged_at_utc) VALUES (%s,%s,%s,%s,%s,%s)"
)
_MENU_STEP_ATTEMPT_COLUMNS = (
    "publication_id,step_name,attempt_number,request_fingerprint,"
    "idempotency_key,outcome,provider_menu_id,error_code,attempted_at_utc,"
    "correlation_id"
)
_MENU_STEP_ATTEMPTS_SELECT_SQL = (
    f"SELECT {_MENU_STEP_ATTEMPT_COLUMNS} "
    "FROM line_rich_menu_publication_step_attempt_events "
    "WHERE publication_id=%s ORDER BY id ASC"
)
_MENU_STEP_ATTEMPTS_SELECT_BY_STEP_SQL = (
    f"SELECT {_MENU_STEP_ATTEMPT_COLUMNS} "
    "FROM line_rich_menu_publication_step_attempt_events "
    "WHERE publication_id=%s AND step_name=%s ORDER BY attempt_number ASC"
)
_MENU_STEP_ATTEMPT_SELECT_BY_ATTEMPT_SQL = (
    f"SELECT {_MENU_STEP_ATTEMPT_COLUMNS} "
    "FROM line_rich_menu_publication_step_attempt_events "
    "WHERE publication_id=%s AND step_name=%s AND attempt_number=%s"
)
_MENU_STEP_ATTEMPT_SELECT_BY_KEY_SQL = (
    f"SELECT {_MENU_STEP_ATTEMPT_COLUMNS} "
    "FROM line_rich_menu_publication_step_attempt_events "
    "WHERE idempotency_key=%s"
)
_MENU_STEP_ATTEMPT_INSERT_SQL = (
    "INSERT INTO line_rich_menu_publication_step_attempt_events "
    "(publication_id,step_name,attempt_number,request_fingerprint,"
    "idempotency_key,outcome,provider_menu_id,error_code,attempted_at_utc,"
    "correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_MENU_CLEANUP_ANOMALY_COLUMNS = (
    "publication_id,request_fingerprint,idempotency_key,error_code,occurred_at_utc"
)
_MENU_CLEANUP_ANOMALY_SELECT_BY_KEY_SQL = (
    f"SELECT {_MENU_CLEANUP_ANOMALY_COLUMNS} "
    "FROM line_rich_menu_publication_cleanup_anomalies "
    "WHERE idempotency_key=%s"
)
_MENU_CLEANUP_ANOMALY_INSERT_SQL = (
    "INSERT INTO line_rich_menu_publication_cleanup_anomalies "
    "(publication_id,request_fingerprint,idempotency_key,error_code,occurred_at_utc) "
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
_MENU_COUNT_SQL = "SELECT COUNT(*) AS total FROM line_rich_menu_publication_tasks"
_MENU_PUBLISHED_PROVIDER_ID_SQL = (
    "SELECT provider_menu_id FROM ("
    "SELECT line_rich_menu_id AS provider_menu_id,2 AS priority,id "
    "FROM line_rich_menu_publications "
    "WHERE menu_config_id=%s AND status='published' AND is_current=TRUE "
    "AND line_rich_menu_id IS NOT NULL "
    "UNION ALL "
    "SELECT provider_menu_id,1 AS priority,id "
    "FROM line_rich_menu_publication_tasks "
    "WHERE menu_definition_id=%s AND publication_status='published' "
    "AND provider_menu_id IS NOT NULL"
    ") published_menus ORDER BY priority DESC,id DESC LIMIT 1"
)
_MENU_CONFIGURATION_SELECT_SQL = (
    "SELECT revision.definition_snapshot "
    "FROM line_configuration_current AS current "
    "JOIN line_configuration_revisions AS revision "
    "ON revision.id=current.revision_id "
    "WHERE current.configuration_kind='rich_menus' "
    "AND current.revision=%s FOR UPDATE"
)
_MENU_INSERT_SQL = (
    "INSERT INTO line_rich_menu_publication_tasks (menu_definition_id,"
    "configuration_revision,operation,publication_status,definition_snapshot,"
    "idempotency_key,correlation_id,requested_by_actor_id) "
    "VALUES (%s,%s,'publish',%s,%s,%s,%s,%s)"
)
_MENU_PREVIEW_LOCK_SQL = (
    "SELECT id FROM line_rich_menu_publish_previews WHERE id=%s "
    "AND menu_config_id=%s AND config_revision=%s AND config_fingerprint=%s "
    "AND previewed_by_admin_user_id=%s AND publication_id IS NULL "
    "AND canonical_publication_task_id IS NULL FOR UPDATE"
)
_MENU_PREVIEW_CONFIRM_SQL = (
    "UPDATE line_rich_menu_publish_previews SET canonical_publication_task_id=%s,"
    "confirmed_at=UTC_TIMESTAMP() WHERE id=%s AND publication_id IS NULL "
    "AND canonical_publication_task_id IS NULL"
)


__all__ = [
    "MySqlLineConfigurationRepository",
    "MySqlLineRichMenuPublicationRepository",
]
