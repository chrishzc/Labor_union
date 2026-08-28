"""
File: anomaly_root_fact_projection_repository.py
Description: 保存 owner-domain root-fact 異常投影、receipt、snapshot 與 recovery query。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from typing import Iterator

from pymysql.err import IntegrityError, OperationalError

from domains.anomalies.registry import (
    AlertWorkflowStatus,
    CurrentAlertProjection,
)
from domains.anomalies.root_fact_projection import FinanceAnomalyOccurrence
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.anomalies.root_fact_projection_workflow import (
    ProjectionStorageUnavailable,
    RootFactProjectionReceipt,
    StoredRecoveryProjection,
)

_CONSUMER_IDENTITY = "anomaly-root-fact-projector-v1"
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class RootFactProjectionMySqlUnitOfWork(MySqlUnitOfWork):
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


class MySqlRootFactProjectionRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def find_receipt(self, source_event_identity, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _RECEIPT_SELECT_SQL + suffix,
                (source_event_identity,),
            )
            row = cursor.fetchone()
        return None if row is None else _receipt(row)

    def load_current(self, fingerprint, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _CURRENT_SELECT_SQL + suffix,
                (fingerprint.value,),
            )
            row = cursor.fetchone()
        return None if row is None else _projection(row)

    def save_current(self, previous, resulting, candidate) -> None:
        if resulting is None:
            return
        with _cursor(self._connection) as cursor:
            if previous is None:
                _insert_current(cursor, resulting, candidate)
            else:
                _update_current(cursor, previous, resulting, candidate)
            _save_root_snapshot(cursor, resulting, candidate)
            _append_projector_workflow_event(
                cursor,
                previous,
                resulting,
                candidate,
            )

    def append_occurrence(self, occurrence) -> None:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _OCCURRENCE_INSERT_SQL,
                (
                    occurrence.occurrence_fingerprint.value,
                    occurrence.definition_code,
                    occurrence.source_event_identity,
                    occurrence.finance_import_row_id,
                    None,
                    occurrence.source_version,
                    _json_dump(occurrence.bounded_snapshot),
                ),
            )

    def save_receipt(self, receipt) -> None:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (
                    receipt.source_event_identity,
                    receipt.event_payload_fingerprint.value,
                    receipt.alert_fingerprint.value,
                    receipt.source_version,
                    receipt.predicate_active,
                    receipt.workflow_version,
                    receipt.occurrence_recorded,
                    _utc_now(),
                ),
            )

    def save_checkpoint(self, root_fact) -> None:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _CHECKPOINT_UPSERT_SQL,
                (
                    _CONSUMER_IDENTITY,
                    root_fact.source_identity,
                    root_fact.source_event_identity,
                    root_fact.source_version,
                    _utc_now(),
                ),
            )

    def query_recovery(self, fingerprint):
        with _cursor(self._connection) as cursor:
            cursor.execute(_RECOVERY_SELECT_SQL, (fingerprint.value,))
            row = cursor.fetchone()
            if row is None:
                return None
            occurrences = _load_occurrences(cursor, row)
            workflow = _load_workflow(cursor, fingerprint)
        return StoredRecoveryProjection(
            projection=_projection(row),
            root_fact_snapshot=_root_snapshot(row),
            projection_freshness=str(row["projection_freshness"]),
            occurrence_timeline=occurrences,
            workflow_timeline=workflow,
        )


@contextmanager
def _cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except (OperationalError, IntegrityError) as error:
        _raise_storage_error(error)


def _raise_storage_error(error) -> None:
    code = int(error.args[0]) if error.args else 0
    retryable = code in _RETRYABLE_MYSQL_CODES or code == 1062
    message = "anomaly projector storage is temporarily unavailable"
    if not retryable:
        message = "anomaly projector storage transaction failed"
    raise ProjectionStorageUnavailable(message, retryable=retryable) from error


def _receipt(row) -> RootFactProjectionReceipt:
    return RootFactProjectionReceipt(
        source_event_identity=str(row["source_event_identity"]),
        event_payload_fingerprint=PreviewFingerprint(
            str(row["event_payload_fingerprint"])
        ),
        alert_fingerprint=PreviewFingerprint(str(row["alert_fingerprint"])),
        source_version=int(row["source_version"]),
        predicate_active=bool(row["predicate_active"]),
        workflow_version=(
            None
            if row["workflow_version"] is None
            else int(row["workflow_version"])
        ),
        occurrence_recorded=bool(row["occurrence_recorded"]),
    )


def _projection(row) -> CurrentAlertProjection:
    return CurrentAlertProjection(
        fingerprint=PreviewFingerprint(str(row["fingerprint"])),
        definition_code=str(row["definition_code"]),
        source_identity=str(row["source_identity"]),
        source_version=int(row["source_version"]),
        predicate_active=bool(row["predicate_active"]),
        workflow_status=AlertWorkflowStatus(str(row["workflow_status"])),
        workflow_version=int(row["workflow_version"]),
    )


def _insert_current(cursor, resulting, candidate) -> None:
    cursor.execute(
        _CURRENT_INSERT_SQL,
        (
            resulting.fingerprint.value,
            resulting.definition_code,
            candidate.source_domain,
            resulting.source_identity,
            resulting.source_version,
            resulting.predicate_active,
            resulting.workflow_status.value,
            resulting.workflow_version,
            _json_dump(candidate.root_fact_snapshot),
        ),
    )


# Kept cohesive because CAS and workflow actor reset share one invariant.
def _update_current(cursor, previous, resulting, candidate) -> None:
    if previous.workflow_status is resulting.workflow_status:
        _update_current_without_workflow_change(
            cursor,
            previous,
            resulting,
            candidate,
        )
        return
    actor_fields = _projector_actor_fields(resulting)
    cursor.execute(
        _CURRENT_UPDATE_SQL,
        (
            resulting.source_version,
            candidate.source_domain,
            resulting.predicate_active,
            resulting.workflow_status.value,
            resulting.workflow_version,
            *actor_fields,
            _json_dump(candidate.root_fact_snapshot),
            previous.fingerprint.value,
            previous.workflow_version,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise ProjectionStorageUnavailable("anomaly projection changed concurrently")


def _update_current_without_workflow_change(
    cursor,
    previous,
    resulting,
    candidate,
) -> None:
    cursor.execute(
        _CURRENT_FACT_UPDATE_SQL,
        (
            resulting.source_version,
            candidate.source_domain,
            resulting.predicate_active,
            resulting.workflow_version,
            _json_dump(candidate.root_fact_snapshot),
            previous.fingerprint.value,
            previous.workflow_version,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise ProjectionStorageUnavailable("anomaly projection changed concurrently")


def _save_root_snapshot(cursor, resulting, candidate) -> None:
    snapshot = candidate.root_fact_snapshot
    cursor.execute(
        _ROOT_SNAPSHOT_UPSERT_SQL,
        (
            resulting.fingerprint.value,
            candidate.source_event_identity,
            candidate.desired.source_version,
            _mysql_datetime(snapshot["occurred_at"]),
            snapshot["root_condition_active"],
            snapshot["integrity_blocker_active"],
            snapshot["amount_delta_ntd"],
            snapshot["finance_import_row_id"],
            snapshot["finance_import_batch_id"],
            _json_dump(snapshot["affected_order_identities"]),
            _json_dump(snapshot["affected_obligation_identities"]),
            _json_dump(snapshot["domain_blockers"]),
            _json_dump(snapshot["reason_codes"]),
        ),
    )


# Kept cohesive because transition detection and immutable audit must agree.
def _append_projector_workflow_event(
    cursor,
    previous,
    resulting,
    candidate,
) -> None:
    action = _projector_action(previous, resulting)
    if action is None:
        return
    cursor.execute(
        _WORKFLOW_EVENT_INSERT_SQL,
        (
            resulting.fingerprint.value,
            action,
            previous.workflow_version,
            resulting.workflow_version,
            "anomaly-projector",
            _projector_reason(action),
            candidate.source_event_identity,
            _projector_event_key(candidate, action),
        ),
    )


def _projector_action(previous, resulting):
    if previous is None:
        return None
    if previous.workflow_status is resulting.workflow_status:
        return None
    if resulting.workflow_status is AlertWorkflowStatus.OPEN:
        return "reopen"
    if not resulting.predicate_active:
        return "auto_resolve"
    return None


def _projector_actor_fields(resulting):
    if resulting.workflow_status is AlertWorkflowStatus.OPEN:
        return None, None, None, None
    if resulting.workflow_status is AlertWorkflowStatus.RESOLVED:
        return None, None, "anomaly-projector", _utc_now()
    return "anomaly-projector", _utc_now(), None, None


def _projector_reason(action):
    if action == "reopen":
        return "Root condition remains active; workflow reopened."
    return "Root condition is inactive; workflow auto-resolved."


def _projector_event_key(candidate, action):
    event_prefix = candidate.event_payload_fingerprint.value[:32]
    return f"root-projector:{event_prefix}:{action}"


def _root_snapshot(row) -> dict[str, object]:
    snapshot = {
        "finance_import_row_id": int(row["finance_import_row_id"]),
        "finance_import_batch_id": int(row["finance_import_batch_id"]),
        "occurred_at": row["source_occurred_at"].isoformat(),
        "amount_delta_ntd": int(row["amount_delta_ntd"]),
        "affected_order_identities": _json_list(
            row["affected_order_identities"]
        ),
        "affected_obligation_identities": _json_list(
            row["affected_obligation_identities"]
        ),
        "domain_blockers": _json_list(row["domain_blockers"]),
        "reason_codes": _json_list(row["reason_codes"]),
        "root_condition_active": bool(row["root_condition_active"]),
        "integrity_blocker_active": bool(row["integrity_blocker_active"]),
        "source_version": int(row["snapshot_source_version"]),
    }
    current_snapshot = _json_object(row["current_display_snapshot"])
    if "original_refund_ledger_entry_id" in current_snapshot:
        original_ledger_id = current_snapshot["original_refund_ledger_entry_id"]
        if original_ledger_id is not None and (
            isinstance(original_ledger_id, bool)
            or not isinstance(original_ledger_id, int)
            or original_ledger_id <= 0
        ):
            raise ValueError("anomaly_projection_data_integrity_violation")
        snapshot["original_refund_ledger_entry_id"] = original_ledger_id
    recovery_bindings = current_snapshot.get("recovery_bindings")
    if isinstance(recovery_bindings, dict):
        snapshot["recovery_bindings"] = recovery_bindings
    return snapshot


def _load_occurrences(cursor, row):
    cursor.execute(
        _OCCURRENCE_SELECT_SQL,
        (str(row["definition_code"]), int(row["finance_import_row_id"])),
    )
    return tuple(_occurrence(item) for item in cursor.fetchall())


def _occurrence(row):
    snapshot = _json_object(row["bounded_snapshot"])
    return FinanceAnomalyOccurrence(
        occurrence_fingerprint=PreviewFingerprint(
            str(row["occurrence_fingerprint"])
        ),
        definition_code=str(row["definition_code"]),
        source_event_identity=str(row["source_event_identity"]),
        finance_import_row_id=int(row["finance_import_row_id"]),
        finance_import_batch_id=int(snapshot["finance_import_batch_id"]),
        source_version=int(row["source_version"]),
        occurred_at=datetime.fromisoformat(str(snapshot["occurred_at"])),
        bounded_snapshot=snapshot,
    )


def _load_workflow(cursor, fingerprint):
    cursor.execute(_WORKFLOW_SELECT_SQL, (fingerprint.value,))
    return tuple(_workflow_event(item) for item in cursor.fetchall())


def _workflow_event(row):
    return {
        "action": str(row["action"]),
        "resulting_workflow_version": int(row["resulting_workflow_version"]),
        "actor": str(row["actor"]),
        "reason": str(row["reason"]),
        "created_at": row["created_at"].isoformat(),
    }


def _json_object(value) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("anomaly_projection_data_integrity_violation")
    return parsed


def _json_list(value) -> list[str]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("anomaly_projection_data_integrity_violation")
    return parsed


def _json_dump(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _mysql_datetime(value):
    return datetime.fromisoformat(str(value)).astimezone(timezone.utc).replace(
        tzinfo=None
    )


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


_RECEIPT_SELECT_SQL = (
    "SELECT source_event_identity,event_payload_fingerprint,alert_fingerprint,"
    "source_version,predicate_active,workflow_version,occurrence_recorded "
    "FROM anomaly_root_fact_projection_receipts "
    "WHERE source_event_identity=%s"
)
_CURRENT_SELECT_SQL = (
    "SELECT fingerprint,definition_code,source_identity,source_version,"
    "predicate_active,workflow_status,workflow_version "
    "FROM anomaly_current_alerts WHERE fingerprint=%s"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO anomaly_root_fact_projection_receipts "
    "(source_event_identity,event_payload_fingerprint,alert_fingerprint,"
    "source_version,predicate_active,workflow_version,occurrence_recorded,"
    "processed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
)
_CURRENT_INSERT_SQL = (
    "INSERT INTO anomaly_current_alerts "
    "(fingerprint,definition_code,definition_version,source_domain,"
    "source_identity,source_version,predicate_active,workflow_status,"
    "workflow_version,projection_version,display_snapshot) "
    "VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,1,%s)"
)
_CURRENT_UPDATE_SQL = (
    "UPDATE anomaly_current_alerts SET source_version=%s,source_domain=%s,predicate_active=%s,"
    "workflow_status=%s,workflow_version=%s,projection_version=projection_version+1,"
    "claimed_by=%s,claimed_at=%s,resolved_by=%s,resolved_at=%s,"
    "display_snapshot=%s WHERE fingerprint=%s AND workflow_version=%s"
)
_CURRENT_FACT_UPDATE_SQL = (
    "UPDATE anomaly_current_alerts SET source_version=%s,source_domain=%s,predicate_active=%s,"
    "workflow_version=%s,projection_version=projection_version+1,"
    "display_snapshot=%s WHERE fingerprint=%s AND workflow_version=%s"
)
_ROOT_SNAPSHOT_UPSERT_SQL = (
    "INSERT INTO anomaly_root_fact_snapshots "
    "(alert_fingerprint,source_event_identity,source_version,source_occurred_at,"
    "root_condition_active,integrity_blocker_active,amount_delta_ntd,"
    "finance_import_row_id,"
    "finance_import_batch_id,affected_order_identities,"
    "affected_obligation_identities,domain_blockers,reason_codes) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE source_event_identity=VALUES(source_event_identity),"
    "source_version=VALUES(source_version),source_occurred_at=VALUES(source_occurred_at),"
    "root_condition_active=VALUES(root_condition_active),"
    "integrity_blocker_active=VALUES(integrity_blocker_active),"
    "amount_delta_ntd=VALUES(amount_delta_ntd),"
    "finance_import_batch_id=VALUES(finance_import_batch_id),"
    "affected_order_identities=VALUES(affected_order_identities),"
    "affected_obligation_identities=VALUES(affected_obligation_identities),"
    "domain_blockers=VALUES(domain_blockers),reason_codes=VALUES(reason_codes),"
    "projection_freshness='current'"
)
_OCCURRENCE_INSERT_SQL = (
    "INSERT INTO finance_anomaly_occurrences "
    "(occurrence_fingerprint,definition_code,source_event_identity,"
    "finance_import_row_id,finance_import_batch_id,source_version,bounded_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s)"
)
_CHECKPOINT_UPSERT_SQL = (
    "INSERT INTO anomaly_consumer_checkpoints "
    "(consumer_identity,partition_identity,source_event_identity,source_version,"
    "processed_at) VALUES (%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE source_event_identity=VALUES(source_event_identity),"
    "source_version=VALUES(source_version),processed_at=VALUES(processed_at)"
)
_WORKFLOW_EVENT_INSERT_SQL = (
    "INSERT INTO anomaly_workflow_events "
    "(alert_fingerprint,action,expected_workflow_version,"
    "resulting_workflow_version,actor,reason,correlation_id,idempotency_key) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
)
_RECOVERY_SELECT_SQL = (
    "SELECT current.fingerprint,current.definition_code,current.source_identity,"
    "current.source_version,current.predicate_active,current.workflow_status,"
    "current.workflow_version,current.display_snapshot AS current_display_snapshot,"
    "snapshot.source_version AS snapshot_source_version,"
    "snapshot.source_occurred_at,snapshot.root_condition_active,"
    "snapshot.integrity_blocker_active,snapshot.amount_delta_ntd,"
    "snapshot.finance_import_row_id,"
    "snapshot.finance_import_batch_id,snapshot.affected_order_identities,"
    "snapshot.affected_obligation_identities,snapshot.domain_blockers,"
    "snapshot.reason_codes,snapshot.projection_freshness "
    "FROM anomaly_current_alerts current "
    "JOIN anomaly_root_fact_snapshots snapshot "
    "ON snapshot.alert_fingerprint=current.fingerprint "
    "WHERE current.fingerprint=%s"
)
_OCCURRENCE_SELECT_SQL = (
    "SELECT occurrence_fingerprint,definition_code,source_event_identity,"
    "finance_import_row_id,finance_import_batch_id,source_version,bounded_snapshot "
    "FROM finance_anomaly_occurrences "
    "WHERE definition_code=%s AND finance_import_row_id=%s ORDER BY id"
)
_WORKFLOW_SELECT_SQL = (
    "SELECT action,resulting_workflow_version,actor,reason,created_at "
    "FROM anomaly_workflow_events WHERE alert_fingerprint=%s ORDER BY id"
)


__all__ = [
    "MySqlRootFactProjectionRepository",
    "RootFactProjectionMySqlUnitOfWork",
]
