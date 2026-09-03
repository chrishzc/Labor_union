"""
File: import_warning_tracking_repository.py
Description: 實作匯入警示追蹤 task、事件、receipt 與 outbox 的 MySQL 存取。
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import replace
from typing import Iterator

from domains.anomalies.import_warning_tracking import ImportWarningTrackingStatus
from subsystems.anomalies.import_warning_tracking_workflow import (
    ImportWarningTask,
    WarningTransitionPreview,
    WarningTransitionReceipt,
    WarningTransitionRequest,
)


class MySqlImportWarningTrackingRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def query_tasks(self, *, active_only: bool, limit: int, offset: int) -> tuple[ImportWarningTask, ...]:
        predicate = "WHERE t.tracking_status NOT IN ('closed','auto_resolved')" if active_only else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _TASK_SELECT.format(predicate=predicate),
                (limit, offset),
            )
            return tuple(_task(row) for row in cursor.fetchall())

    def load_task(self, occurrence_identity: str, *, for_update: bool) -> ImportWarningTask | None:
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(_TASK_BY_IDENTITY + suffix, (occurrence_identity,))
            row = cursor.fetchone()
        return _task(row) if row is not None else None

    def replay(
        self,
        request: WarningTransitionRequest,
    ) -> WarningTransitionReceipt | None:
        fingerprint = _fingerprint(request)
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot "
                "FROM import_warning_tracking_receipts WHERE idempotency_key=%s",
                (request.idempotency_key.value,),
            )
            receipt = cursor.fetchone()
        if receipt is None:
            return None
        if str(receipt["command_fingerprint"]) != fingerprint:
            raise ValueError("import_warning_idempotency_mismatch")
        return replace(_receipt(receipt["result_snapshot"]), replayed=True)

    def lookup_receipt(self, receipt_identity: str) -> WarningTransitionReceipt | None:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT r.result_snapshot,e.event_identity "
                "FROM import_warning_tracking_receipts r "
                "JOIN import_warning_tracking_events e ON e.id=r.tracking_event_id "
                "WHERE e.event_identity=%s",
                (receipt_identity,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        receipt = _receipt(row["result_snapshot"])
        if receipt.receipt_identity != str(row["event_identity"]):
            raise ValueError("import_warning_receipt_invalid")
        return receipt

    def apply_transition(self, task: ImportWarningTask, request: WarningTransitionRequest, preview: WarningTransitionPreview) -> WarningTransitionReceipt:
        fingerprint = _fingerprint(request)
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM import_warning_tracking_receipts WHERE idempotency_key=%s",
                (request.idempotency_key.value,),
            )
            receipt = cursor.fetchone()
            if receipt is not None:
                if str(receipt["command_fingerprint"]) != fingerprint:
                    raise ValueError("import_warning_idempotency_mismatch")
                return replace(_receipt(receipt["result_snapshot"]), replayed=True)
            cursor.execute("SELECT id FROM import_warning_occurrences WHERE occurrence_identity=%s FOR UPDATE", (task.occurrence_identity,))
            occurrence = cursor.fetchone()
            if occurrence is None:
                raise ValueError("import_warning_not_found")
            event_identity = _identity("import-warning-event", request.idempotency_key.value)
            cursor.execute(
                "INSERT INTO import_warning_tracking_events (event_identity,occurrence_id,action,before_status,after_status,expected_version,resulting_version,actor_kind,actor_identity,reason_code,note,evidence_reference,command_fingerprint,idempotency_key,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (event_identity, occurrence["id"], preview.resulting_status.value, task.tracking_status.value, preview.resulting_status.value, preview.expected_version, preview.resulting_version, "system" if request.actor.actor_id == "system" else "union_operator", request.actor.actor_id, request.reason_code, request.note, request.evidence_reference, fingerprint, request.idempotency_key.value, request.correlation_id.value),
            )
            event_id = cursor.lastrowid
            cursor.execute(
                "UPDATE import_warning_current_tasks SET tracking_status=%s,tracking_version=%s,last_event_id=%s,last_event_at=CURRENT_TIMESTAMP WHERE occurrence_id=%s AND tracking_version=%s",
                (preview.resulting_status.value, preview.resulting_version, event_id, occurrence["id"], preview.expected_version),
            )
            if int(cursor.rowcount) != 1:
                raise ValueError("import_warning_version_conflict")
            receipt_identity = event_identity
            snapshot = _snapshot(task, preview, request, receipt_identity)
            cursor.execute(
                "INSERT INTO import_warning_tracking_receipts (idempotency_key,command_fingerprint,occurrence_id,tracking_event_id,expected_version,resulting_version,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (request.idempotency_key.value, fingerprint, occurrence["id"], event_id, preview.expected_version, preview.resulting_version, _json(snapshot)),
            )
            cursor.execute(
                "INSERT INTO import_warning_tracking_outbox (tracking_event_id,intent_key,bounded_snapshot) VALUES (%s,%s,%s)",
                (event_id, _identity("import-warning-outbox", event_identity), _json({"occurrence_identity": task.occurrence_identity, "owning_lane": task.owning_lane, "logical_code": task.logical_code, "field_path": task.field_path, "tracking_status": preview.resulting_status.value, "tracking_version": preview.resulting_version})),
            )
        return _receipt(snapshot)


@contextmanager
def _cursor(connection) -> Iterator[object]:
    with connection.cursor() as cursor:
        yield cursor


def _task(row) -> ImportWarningTask:
    issue_codes = json.loads(row["issue_codes"]) if isinstance(row["issue_codes"], str) else row["issue_codes"]
    return ImportWarningTask(str(row["occurrence_identity"]), str(row["owning_lane"]), str(row["logical_code"]), str(row["field_path"]), str(row["subject"]), tuple(str(item) for item in issue_codes), ImportWarningTrackingStatus(str(row["tracking_status"])), int(row["tracking_version"]), None)


def _fingerprint(request: WarningTransitionRequest) -> str:
    return _identity("import-warning-command", _json({"occurrence_identity": request.occurrence_identity, "expected_version": request.expected_version, "target_status": request.target_status.value, "reason_code": request.reason_code, "note": request.note, "evidence_reference": request.evidence_reference, "actor": request.actor.actor_id}))


def _identity(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _snapshot(task: ImportWarningTask, preview: WarningTransitionPreview, request: WarningTransitionRequest, receipt_identity: str) -> dict[str, object]:
    return {"occurrence_identity": preview.occurrence_identity, "before_status": task.tracking_status.value, "after_status": preview.resulting_status.value, "resulting_version": preview.resulting_version, "receipt_identity": receipt_identity, "correlation_id": request.correlation_id.value}


def _receipt(value: object) -> WarningTransitionReceipt:
    snapshot = json.loads(value) if isinstance(value, str) else value
    try:
        receipt = WarningTransitionReceipt(str(snapshot["occurrence_identity"]), ImportWarningTrackingStatus(str(snapshot["before_status"])), ImportWarningTrackingStatus(str(snapshot["after_status"])), int(snapshot["resulting_version"]), str(snapshot["receipt_identity"]), str(snapshot["correlation_id"]), False)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("import_warning_receipt_invalid") from error
    if re.fullmatch(r"[0-9a-f]{64}", receipt.receipt_identity) is None:
        raise ValueError("import_warning_receipt_invalid")
    return receipt


_TASK_FIELDS = "o.occurrence_identity,o.owning_lane,o.logical_code,o.field_path,o.subject,o.issue_codes,t.tracking_status,t.tracking_version"
_TASK_SELECT = f"SELECT {_TASK_FIELDS} FROM import_warning_current_tasks t JOIN import_warning_occurrences o ON o.id=t.occurrence_id {{predicate}} ORDER BY t.last_event_at DESC LIMIT %s OFFSET %s"
_TASK_BY_IDENTITY = f"SELECT {_TASK_FIELDS} FROM import_warning_current_tasks t JOIN import_warning_occurrences o ON o.id=t.occurrence_id WHERE o.occurrence_identity=%s"


__all__ = ["MySqlImportWarningTrackingRepository"]
