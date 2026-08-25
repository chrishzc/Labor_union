"""File: staff_leave_intake_repository.py
Description: 保存 Scheduling 月嫂請假待辦的 aggregate、事件與冪等 receipt。"""

from __future__ import annotations

import json
from typing import Any

from domains.scheduling.staff_leave_intake import StaffLeaveRequestStatus
from subsystems.scheduling.staff_leave_intake_workflow import StaffLeaveRequestSnapshot


class MySqlStaffLeaveIntakeRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def replay(self, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SQL, (key,))
            row = cursor.fetchone()
        if row is None:
            return None
        if str(row["request_fingerprint"]) != fingerprint:
            raise ValueError("leave_request_idempotency_conflict")
        return _snapshot(row)

    def create(self, command, fingerprint: str) -> StaffLeaveRequestSnapshot:
        with self._connection.cursor() as cursor:
            intent = command.intent
            cursor.execute(
                _ROOT_INSERT_SQL,
                (command.staff_id, command.line_user_id, intent.leave_start_date,
                 intent.leave_end_date, intent.reason.strip(), fingerprint),
            )
            request_id = int(cursor.lastrowid)
            cursor.execute(
                _EVENT_INSERT_SQL,
                (request_id, 1, "submitted", f"line:{command.line_user_id}", intent.reason.strip()),
            )
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (command.idempotency_key, request_id, fingerprint, _result_snapshot(request_id, "pending", 1)),
            )
            cursor.execute(_ROOT_SQL, (request_id,))
            return _snapshot(cursor.fetchone())

    def load_for_update(self, request_id: int) -> StaffLeaveRequestSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ROOT_SQL + " FOR UPDATE", (request_id,))
            row = cursor.fetchone()
        return _snapshot(row) if row is not None else None

    def load(self, request_id: int) -> StaffLeaveRequestSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ROOT_SQL, (request_id,))
            row = cursor.fetchone()
        return _snapshot(row) if row is not None else None

    def load_for_staff(self, request_id: int, staff_id: int) -> StaffLeaveRequestSnapshot | None:
        """Read back only a request owned by the verified staff subject."""
        with self._connection.cursor() as cursor:
            cursor.execute(_ROOT_SQL + " AND staff_id=%s", (request_id, staff_id))
            row = cursor.fetchone()
        return _snapshot(row) if row is not None else None

    def replay_mutation(self, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot | None:
        return self.replay(key, fingerprint)

    def list_requests(self, status: str, limit: int) -> list[dict[str, Any]]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.id,r.staff_id,s.name AS staff_name,r.leave_start_date,r.leave_end_date,"
                "r.request_reason,r.request_status,r.aggregate_version "
                "FROM scheduling_staff_leave_request_aggregates r JOIN staff s ON s.id=r.staff_id "
                "WHERE r.request_status=%s ORDER BY r.created_at,r.id LIMIT %s",
                (status, limit),
            )
            return list(cursor.fetchall() or ())

    def transition(self, snapshot, target, reason: str, actor_id: str, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(_ROOT_TRANSITION_SQL, (target.value, snapshot.request_id, snapshot.version))
            if cursor.rowcount != 1:
                raise ValueError("leave_request_stale")
            version = snapshot.version + 1
            cursor.execute(_EVENT_INSERT_SQL, (snapshot.request_id, version, target.value, actor_id, reason))
            cursor.execute(_RECEIPT_INSERT_SQL, (key, snapshot.request_id, fingerprint, _result_snapshot(snapshot.request_id, target.value, version)))
            cursor.execute(_ROOT_SQL, (snapshot.request_id,))
            return _snapshot(cursor.fetchone())

    def resolve(self, snapshot, receipt_key: str, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(_CANONICAL_RECEIPT_SQL, (receipt_key, snapshot.staff_id))
            if cursor.fetchone() is None:
                raise ValueError("leave_request_receipt_conflict")
            try:
                cursor.execute(_RESOLUTION_LINK_SQL, (snapshot.request_id, receipt_key))
            except Exception as error:
                if _duplicate_key(error):
                    raise ValueError("leave_request_receipt_conflict") from error
                raise
            cursor.execute(_ROOT_TRANSITION_SQL, (StaffLeaveRequestStatus.RESOLVED.value, snapshot.request_id, snapshot.version))
            if cursor.rowcount != 1:
                raise ValueError("leave_request_stale")
            version = snapshot.version + 1
            cursor.execute(_EVENT_INSERT_SQL, (snapshot.request_id, version, "resolved", "leave-substitution-receipt", receipt_key))
            cursor.execute(_RECEIPT_INSERT_SQL, (key, snapshot.request_id, fingerprint, _result_snapshot(snapshot.request_id, StaffLeaveRequestStatus.RESOLVED.value, version, receipt_key)))
            cursor.execute(_ROOT_SQL, (snapshot.request_id,))
            return _snapshot(cursor.fetchone())


def _snapshot(row) -> StaffLeaveRequestSnapshot:
    return StaffLeaveRequestSnapshot(
        int(row["id"]), int(row["staff_id"]), str(row["line_user_id"]),
        StaffLeaveRequestStatus(str(row["request_status"])), int(row["aggregate_version"]),
        str(row["request_fingerprint"]),
        row.get("leave_start_date") if hasattr(row, "get") else row["leave_start_date"],
        row.get("leave_end_date") if hasattr(row, "get") else row["leave_end_date"],
        str((row.get("request_reason") if hasattr(row, "get") else row["request_reason"]) or ""),
    )


_ROOT_COLUMNS = "id,staff_id,line_user_id,leave_start_date,leave_end_date,request_reason,request_status,aggregate_version,request_fingerprint"
_ROOT_SQL = f"SELECT {_ROOT_COLUMNS} FROM scheduling_staff_leave_request_aggregates WHERE id=%s"
_RECEIPT_ROOT_COLUMNS = (
    "a.id,a.staff_id,a.line_user_id,a.leave_start_date,a.leave_end_date,"
    "a.request_reason,a.request_status,a.aggregate_version,a.request_fingerprint"
)
_RECEIPT_SQL = (
    f"SELECT r.request_fingerprint,{_RECEIPT_ROOT_COLUMNS} "
    "FROM scheduling_staff_leave_request_receipts r "
    "JOIN scheduling_staff_leave_request_aggregates a ON a.id=r.request_id "
    "WHERE r.idempotency_key=%s"
)
_ROOT_INSERT_SQL = "INSERT INTO scheduling_staff_leave_request_aggregates (staff_id,line_user_id,leave_start_date,leave_end_date,request_reason,request_status,request_fingerprint) VALUES (%s,%s,%s,%s,%s,'pending',%s)"
_EVENT_INSERT_SQL = "INSERT INTO scheduling_staff_leave_request_events (request_id,aggregate_version,event_type,actor_id,reason) VALUES (%s,%s,%s,%s,%s)"
_RECEIPT_INSERT_SQL = "INSERT INTO scheduling_staff_leave_request_receipts (idempotency_key,request_id,request_fingerprint,result_snapshot) VALUES (%s,%s,%s,%s)"
_ROOT_TRANSITION_SQL = "UPDATE scheduling_staff_leave_request_aggregates SET request_status=%s,aggregate_version=aggregate_version+1 WHERE id=%s AND aggregate_version=%s"
_RESOLUTION_LINK_SQL = "INSERT INTO scheduling_staff_leave_request_resolution_links (request_id,leave_substitution_receipt_key) VALUES (%s,%s)"
_CANONICAL_RECEIPT_SQL = (
    "SELECT b.batch_key FROM scheduling_leave_substitution_batches b "
    "JOIN scheduling_leave_substitution_outcomes o ON o.batch_key=b.batch_key "
    "WHERE b.batch_key=%s AND o.original_staff_id=%s LIMIT 1 FOR UPDATE"
)


def _result_snapshot(request_id: int, status: str, version: int, receipt_key: str | None = None) -> str:
    payload: dict[str, object] = {"request_id": request_id, "status": status, "version": version}
    if receipt_key is not None:
        payload["leave_substitution_receipt_key"] = receipt_key
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _duplicate_key(error: Exception) -> bool:
    arguments = getattr(error, "args", ())
    return bool(arguments and arguments[0] == 1062)
