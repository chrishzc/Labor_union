"""MySQL persistence for Anomalies projection, workflow, and query."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from typing import Iterator, Mapping

from pymysql.err import IntegrityError, OperationalError

from domains.anomalies.registry import (
    AlertWorkflowStatus,
    CurrentAlertProjection,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.anomalies.alert_workflow import (
    AnomalyDetail,
    AnomalySummary,
    StoredWorkflowEvent,
)

_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class AnomalyRepositoryUnavailable(RuntimeError):
    """Signals a transient MySQL failure suitable for retry."""


class AnomalyMySqlUnitOfWork(MySqlUnitOfWork):
    def __enter__(self):
        try:
            return super().__enter__()
        except OperationalError as error:
            _raise_if_retryable(error)
            raise

    def commit(self) -> None:
        try:
            super().commit()
        except OperationalError as error:
            _raise_if_retryable(error)
            raise


class MySqlAnomalyRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load_current(self, fingerprint, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _CURRENT_SELECT_SQL + suffix,
                (fingerprint.value,),
            )
            row = cursor.fetchone()
        return None if row is None else (_projection(row), _json_object(row["display_snapshot"]))

    def checkpoint_matches(self, request) -> bool:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT source_event_identity,source_version "
                "FROM anomaly_consumer_checkpoints "
                "WHERE consumer_identity=%s AND partition_identity=%s "
                "FOR UPDATE",
                (request.consumer_identity, request.partition_identity),
            )
            row = cursor.fetchone()
        if row is None:
            return False
        stored_version = int(row["source_version"])
        if stored_version > request.desired.source_version:
            raise ValueError("anomaly_projection_stale")
        if stored_version == request.desired.source_version:
            return str(row["source_event_identity"]) == request.source_event_identity
        return False

    # Kept cohesive so insert/update always follows the reducer's desired state.
    def save_projection(
        self,
        definition,
        previous,
        resulting,
        display_snapshot,
    ) -> None:
        if resulting is None:
            return
        with _cursor(self._connection) as cursor:
            if previous is None:
                _insert_projection(
                    cursor,
                    definition,
                    resulting,
                    display_snapshot,
                )
                return
            _update_projection(
                cursor,
                previous,
                resulting,
                display_snapshot,
            )

    def append_projector_event(self, previous, resulting, request) -> None:
        action = _projector_action(previous, resulting)
        if action is None:
            return
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _WORKFLOW_EVENT_INSERT_SQL,
                (
                    resulting.fingerprint.value,
                    action,
                    previous.workflow_version,
                    resulting.workflow_version,
                    "anomaly-projector",
                    _projector_reason(action),
                    request.source_event_identity,
                    _projector_key(request, action),
                ),
            )

    def save_checkpoint(self, request) -> None:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO anomaly_consumer_checkpoints "
                "(consumer_identity,partition_identity,source_event_identity,"
                "source_version,processed_at) VALUES (%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "source_event_identity=VALUES(source_event_identity),"
                "source_version=VALUES(source_version),"
                "processed_at=VALUES(processed_at)",
                (
                    request.consumer_identity,
                    request.partition_identity,
                    request.source_event_identity,
                    request.desired.source_version,
                    _utc_now(),
                ),
            )

    def find_workflow_event(self, key):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT event.alert_fingerprint,event.action,"
                "event.expected_workflow_version,event.resulting_workflow_version,"
                "event.actor,event.reason,current.workflow_status "
                "FROM anomaly_workflow_events event "
                "JOIN anomaly_current_alerts current "
                "ON current.fingerprint=event.alert_fingerprint "
                "WHERE event.idempotency_key=%s FOR UPDATE",
                (key.value,),
            )
            row = cursor.fetchone()
        return None if row is None else _stored_workflow_event(row)

    # Kept cohesive so workflow CAS and immutable event cannot separate.
    def save_workflow(self, previous, resulting, request, action) -> None:
        with _cursor(self._connection) as cursor:
            _update_workflow_projection(
                cursor,
                previous,
                resulting,
                request,
                action,
            )
            cursor.execute(
                _WORKFLOW_EVENT_INSERT_SQL,
                (
                    previous.fingerprint.value,
                    action,
                    previous.workflow_version,
                    resulting.workflow_version,
                    request.actor.actor_id,
                    request.reason,
                    request.correlation_id.value,
                    request.idempotency_key.value,
                ),
            )

    def query_summaries(self, *, active_only, limit=100, offset=0):
        predicate = "WHERE predicate_active=1" if active_only else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _SUMMARY_SELECT_SQL.format(predicate=predicate),
                (limit, offset),
            )
            rows = tuple(cursor.fetchall())
        return tuple(_summary(row) for row in rows)

    def query_detail(self, fingerprint):
        with _cursor(self._connection) as cursor:
            cursor.execute(_CURRENT_SELECT_SQL, (fingerprint.value,))
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                "SELECT action,expected_workflow_version,"
                "resulting_workflow_version,actor,reason,correlation_id,"
                "created_at FROM anomaly_workflow_events "
                "WHERE alert_fingerprint=%s ORDER BY id",
                (fingerprint.value,),
            )
            timeline = tuple(_timeline_event(item) for item in cursor.fetchall())
        return AnomalyDetail(_summary(row), timeline, ())


@contextmanager
def _cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except OperationalError as error:
        _raise_if_retryable(error)
        raise
    except IntegrityError as error:
        if error.args and int(error.args[0]) == 1062:
            raise AnomalyRepositoryUnavailable(
                "concurrent anomaly write requires exact retry"
            ) from error
        raise


def _raise_if_retryable(error) -> None:
    code = int(error.args[0]) if error.args else 0
    if code in _RETRYABLE_MYSQL_CODES:
        raise AnomalyRepositoryUnavailable(
            "Anomalies MySQL transaction is temporarily unavailable"
        ) from error


def _projection(row):
    return CurrentAlertProjection(
        PreviewFingerprint(str(row["fingerprint"])),
        str(row["definition_code"]),
        str(row["source_identity"]),
        int(row["source_version"]),
        bool(row["predicate_active"]),
        AlertWorkflowStatus(str(row["workflow_status"])),
        int(row["workflow_version"]),
    )


def _insert_projection(cursor, definition, resulting, display_snapshot):
    actor_fields = _workflow_actor_fields(resulting.workflow_status)
    cursor.execute(
        _CURRENT_INSERT_SQL,
        (
            resulting.fingerprint.value,
            definition.code,
            definition.source_domain,
            resulting.source_identity,
            resulting.source_version,
            resulting.predicate_active,
            resulting.workflow_status.value,
            resulting.workflow_version,
            *actor_fields,
            _json_dump(display_snapshot),
        ),
    )


def _update_projection(cursor, previous, resulting, display_snapshot):
    actor_fields = _workflow_actor_fields(resulting.workflow_status)
    cursor.execute(
        _CURRENT_UPDATE_SQL,
        (
            resulting.source_version,
            resulting.predicate_active,
            resulting.workflow_status.value,
            resulting.workflow_version,
            *actor_fields,
            _json_dump(display_snapshot),
            previous.fingerprint.value,
            previous.workflow_version,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise AnomalyRepositoryUnavailable("anomaly projection changed concurrently")


# Kept cohesive because all actor fields belong to one workflow-state invariant.
def _update_workflow_projection(
    cursor,
    previous,
    resulting,
    request,
    action,
):
    claimed_by = request.actor.actor_id if action == "claim" else None
    claimed_at = _utc_now() if action == "claim" else None
    resolved_by = request.actor.actor_id if action == "resolve" else None
    resolved_at = _utc_now() if action == "resolve" else None
    cursor.execute(
        "UPDATE anomaly_current_alerts SET workflow_status=%s,"
        "workflow_version=%s,claimed_by=%s,claimed_at=%s,"
        "resolved_by=%s,resolved_at=%s "
        "WHERE fingerprint=%s AND workflow_version=%s",
        (
            resulting.workflow_status.value,
            resulting.workflow_version,
            claimed_by,
            claimed_at,
            resolved_by,
            resolved_at,
            previous.fingerprint.value,
            previous.workflow_version,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise AnomalyRepositoryUnavailable("anomaly workflow changed concurrently")


def _workflow_actor_fields(status):
    if status is AlertWorkflowStatus.OPEN:
        return None, None, None, None
    if status is AlertWorkflowStatus.CLAIMED:
        return "anomaly-projector", _utc_now(), None, None
    return None, None, "anomaly-projector", _utc_now()


def _projector_action(previous, resulting):
    if previous is None or previous.workflow_status is resulting.workflow_status:
        return None
    if resulting.workflow_status is AlertWorkflowStatus.OPEN:
        return "reopen"
    if not resulting.predicate_active:
        return "auto_resolve"
    return None


def _projector_reason(action):
    return (
        "Root condition is active; workflow reopened."
        if action == "reopen"
        else "Root condition is inactive; workflow auto-resolved."
    )


def _projector_key(request, action):
    return (
        f"anomaly-projector:{request.consumer_identity}:"
        f"{request.partition_identity}:{request.source_event_identity}:{action}"
    )


def _stored_workflow_event(row):
    status = _resulting_status(str(row["action"]), str(row["workflow_status"]))
    return StoredWorkflowEvent(
        PreviewFingerprint(str(row["alert_fingerprint"])),
        str(row["action"]),
        int(row["expected_workflow_version"]),
        int(row["resulting_workflow_version"]),
        status,
        str(row["actor"]),
        str(row["reason"]),
    )


def _resulting_status(action, current_status):
    if action == "claim":
        return AlertWorkflowStatus.CLAIMED
    if action in {"resolve", "auto_resolve"}:
        return AlertWorkflowStatus.RESOLVED
    if action == "reopen":
        return AlertWorkflowStatus.OPEN
    return AlertWorkflowStatus(current_status)


def _summary(row):
    return AnomalySummary(
        _projection(row),
        str(row["source_domain"]),
        "",
        _json_object(row["display_snapshot"]),
    )


def _timeline_event(row):
    return {
        "action": str(row["action"]),
        "expected_workflow_version": int(row["expected_workflow_version"]),
        "resulting_workflow_version": int(row["resulting_workflow_version"]),
        "actor": str(row["actor"]),
        "reason": str(row["reason"]),
        "correlation_id": str(row["correlation_id"]),
        "created_at": row["created_at"],
    }


def _json_object(value) -> Mapping[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("anomaly_projection_data_integrity_violation")
    return parsed


def _json_dump(value):
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


_CURRENT_SELECT_SQL = (
    "SELECT fingerprint,definition_code,source_domain,source_identity,"
    "source_version,predicate_active,workflow_status,workflow_version,"
    "display_snapshot FROM anomaly_current_alerts WHERE fingerprint=%s"
)
_SUMMARY_SELECT_SQL = (
    "SELECT fingerprint,definition_code,source_domain,source_identity,"
    "source_version,predicate_active,workflow_status,workflow_version,"
    "display_snapshot FROM anomaly_current_alerts {predicate} "
    "ORDER BY predicate_active DESC,workflow_status,updated_at DESC "
    "LIMIT %s OFFSET %s"
)
_CURRENT_INSERT_SQL = (
    "INSERT INTO anomaly_current_alerts "
    "(fingerprint,definition_code,definition_version,source_domain,"
    "source_identity,source_version,predicate_active,workflow_status,"
    "workflow_version,projection_version,claimed_by,claimed_at,resolved_by,"
    "resolved_at,display_snapshot) VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,1,"
    "%s,%s,%s,%s,%s)"
)
_CURRENT_UPDATE_SQL = (
    "UPDATE anomaly_current_alerts SET source_version=%s,predicate_active=%s,"
    "workflow_status=%s,workflow_version=%s,projection_version=projection_version+1,"
    "claimed_by=%s,claimed_at=%s,resolved_by=%s,resolved_at=%s,"
    "display_snapshot=%s WHERE fingerprint=%s AND workflow_version=%s"
)
_WORKFLOW_EVENT_INSERT_SQL = (
    "INSERT INTO anomaly_workflow_events "
    "(alert_fingerprint,action,expected_workflow_version,"
    "resulting_workflow_version,actor,reason,correlation_id,idempotency_key) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
)

__all__ = [
    "AnomalyMySqlUnitOfWork",
    "AnomalyRepositoryUnavailable",
    "MySqlAnomalyRepository",
]
