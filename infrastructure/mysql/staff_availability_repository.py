"""MySQL persistence adapter for Scheduling-owned staff availability."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Mapping

from domains.scheduling.staff_availability import (
    StaffAvailabilityAction,
    StaffAvailabilityBlockStatus,
    StaffAvailabilityCandidate,
    StaffAvailabilityConflict,
    StaffAvailabilityDomainError,
    StaffAvailabilityErrorCode,
    StaffAvailabilityFacts,
    StaffAvailabilityIntent,
    StaffUnavailabilityBlock,
    StaffUnavailabilityKind,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, IdempotencyKey
from subsystems.scheduling.staff_availability_workflow import (
    StaffAvailabilityApplyReceipt,
    StaffAvailabilityApplyRequest,
    StaffAvailabilityQuery,
    StoredStaffAvailabilityReceipt,
)


class MySqlStaffAvailabilityRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_blocks(self, query: StaffAvailabilityQuery) -> tuple[StaffUnavailabilityBlock, ...]:
        with self._connection.cursor() as cursor:
            _require_staff(cursor, query.staff_id, for_update=False)
            cursor.execute(_BLOCK_RANGE_SQL, (query.staff_id, query.range_end, query.range_start))
            return tuple(_block_from_row(row) for row in _mapping_rows(cursor.fetchall()))

    def load_facts(self, intent: StaffAvailabilityIntent, *, for_update: bool) -> StaffAvailabilityFacts:
        with self._connection.cursor() as cursor:
            _require_staff(cursor, intent.staff_id, for_update=for_update)
            version = _load_version(cursor, intent.staff_id, for_update)
            target = _load_target(cursor, intent, for_update)
            blocks, conflicts = _load_create_conflicts(cursor, intent, for_update)
            return StaffAvailabilityFacts(intent.staff_id, version, blocks, conflicts, target)

    def load_receipt(self, key: IdempotencyKey) -> StoredStaffAvailabilityReceipt | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return _stored_receipt(row) if row is not None else None

    def create_block(self, intent, candidate, actor, occurred_at):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _BLOCK_INSERT_SQL,
                (
                    intent.staff_id,
                    candidate.kind.value,
                    candidate.start_date,
                    candidate.end_date,
                    intent.reason,
                    actor.actor_id,
                    _database_datetime(occurred_at),
                ),
            )
            block_id = int(cursor.lastrowid)
            return _require_block(cursor, block_id, for_update=False)

    def end_pause(self, target, candidate, actor, occurred_at):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _END_PAUSE_SQL,
                (
                    candidate.end_date,
                    actor.actor_id,
                    _database_datetime(occurred_at),
                    target.block_id,
                    target.staff_id,
                ),
            )
            _require_single_mutation(cursor, StaffAvailabilityErrorCode.STALE)
            return _require_block(cursor, target.block_id, for_update=False)

    def cancel_block(self, target, actor, occurred_at):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CANCEL_BLOCK_SQL,
                (
                    actor.actor_id,
                    _database_datetime(occurred_at),
                    target.block_id,
                    target.staff_id,
                ),
            )
            _require_single_mutation(cursor, StaffAvailabilityErrorCode.STALE)
            return _require_block(cursor, target.block_id, for_update=False)

    def increment_version(self, staff_id: int, expected_version: int) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(_VERSION_INCREMENT_SQL, (staff_id, expected_version))
            _require_single_mutation(cursor, StaffAvailabilityErrorCode.STALE)
        return expected_version + 1

    def append_event(self, request, before, after, aggregate_version, occurred_at):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _EVENT_INSERT_SQL,
                (
                    request.idempotency_key.value,
                    request.intent.staff_id,
                    aggregate_version,
                    after.block_id,
                    _event_type(request.intent.action),
                    _canonical_json(_block_payload(before) or {}),
                    _canonical_json(_block_payload(after)),
                    request.actor.actor_id,
                    request.intent.reason,
                    request.correlation_id.value,
                    _database_datetime(occurred_at),
                ),
            )

    def save_receipt(self, request, request_fingerprint, receipt, occurred_at):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (
                    request.idempotency_key.value,
                    request_fingerprint.value,
                    receipt.preview_fingerprint.value,
                    receipt.staff_id,
                    receipt.aggregate_version,
                    receipt.block.block_id,
                    receipt.action.value,
                    _canonical_json(_receipt_payload(receipt)),
                    request.actor.actor_id,
                    request.intent.reason,
                    request.correlation_id.value,
                    _database_datetime(occurred_at),
                ),
            )

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()


def _load_version(cursor, staff_id, for_update):
    if for_update:
        cursor.execute(_AGGREGATE_ENSURE_SQL, (staff_id,))
    cursor.execute(_AGGREGATE_SELECT_SQL + (" FOR UPDATE" if for_update else ""), (staff_id,))
    row = cursor.fetchone()
    return int(row["aggregate_version"]) if row is not None else 0


def _load_target(cursor, intent, for_update):
    if intent.block_id is None:
        return None
    return _load_block(cursor, intent.block_id, intent.staff_id, for_update)


def _load_create_conflicts(cursor, intent, for_update):
    if intent.action not in {StaffAvailabilityAction.CREATE_LONG_LEAVE, StaffAvailabilityAction.CREATE_PAUSE}:
        return (), ()
    blocks = _overlapping_blocks(cursor, intent, for_update)
    conflicts = [
        StaffAvailabilityConflict("unavailability", str(block.block_id), block.start_date, block.end_date or date.max)
        for block in blocks
    ]
    conflicts.extend(_occupancy_conflicts(cursor, intent))
    return blocks, tuple(conflicts)


def _overlapping_blocks(cursor, intent, for_update):
    cursor.execute(
        _EFFECTIVE_OVERLAP_SQL + (" FOR UPDATE" if for_update else ""),
        (intent.staff_id, intent.start_date, intent.end_date, intent.end_date),
    )
    return tuple(_block_from_row(row) for row in _mapping_rows(cursor.fetchall()))


def _occupancy_conflicts(cursor, intent):
    conflicts = []
    for source_kind, sql in _CONFLICT_QUERIES:
        cursor.execute(sql, (intent.staff_id, intent.start_date, intent.end_date, intent.end_date))
        conflicts.extend(_conflict_from_row(source_kind, row) for row in _mapping_rows(cursor.fetchall()))
    return conflicts


def _conflict_from_row(source_kind, row):
    return StaffAvailabilityConflict(
        source_kind,
        str(row["source_identity"]),
        _as_date(row["start_date"]),
        _as_date(row["end_date"]),
    )


def _require_staff(cursor, staff_id, for_update):
    cursor.execute("SELECT id FROM staff WHERE id=%s" + (" FOR UPDATE" if for_update else ""), (staff_id,))
    if cursor.fetchone() is None:
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.STAFF_NOT_FOUND)


def _load_block(cursor, block_id, staff_id, for_update):
    cursor.execute(
        _BLOCK_ID_SQL + (" FOR UPDATE" if for_update else ""),
        (block_id, staff_id),
    )
    row = cursor.fetchone()
    return _block_from_row(row) if row is not None else None


def _require_block(cursor, block_id, for_update):
    cursor.execute(_BLOCK_BY_ID_SQL + (" FOR UPDATE" if for_update else ""), (block_id,))
    row = cursor.fetchone()
    if row is None:
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.BLOCK_NOT_FOUND)
    return _block_from_row(row)


def _block_from_row(row):
    return StaffUnavailabilityBlock(
        int(row["id"]),
        int(row["staff_id"]),
        StaffUnavailabilityKind(str(row["block_kind"])),
        _as_date(row["start_date"]),
        _as_optional_date(row["end_date"]),
        StaffAvailabilityBlockStatus(str(row["status"])),
        str(row["reason"]),
    )


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = StaffAvailabilityApplyReceipt(
        int(payload["staff_id"]),
        StaffAvailabilityAction(str(payload["action"])),
        _block_from_payload(payload["block"]),
        int(payload["aggregate_version"]),
        PreviewFingerprint(str(payload["preview_fingerprint"])),
        IdempotencyKey(str(row["idempotency_key"])),
    )
    return StoredStaffAvailabilityReceipt(PreviewFingerprint(str(row["request_fingerprint"])), receipt)


def _block_from_payload(payload):
    return StaffUnavailabilityBlock(
        int(payload["block_id"]),
        int(payload["staff_id"]),
        StaffUnavailabilityKind(str(payload["kind"])),
        date.fromisoformat(str(payload["start_date"])),
        date.fromisoformat(str(payload["end_date"])) if payload["end_date"] else None,
        StaffAvailabilityBlockStatus(str(payload["status"])),
        str(payload["reason"]),
    )


def _receipt_payload(receipt):
    return {
        "staff_id": receipt.staff_id,
        "action": receipt.action.value,
        "block": _block_payload(receipt.block),
        "aggregate_version": receipt.aggregate_version,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _event_type(action):
    return {
        StaffAvailabilityAction.CREATE_LONG_LEAVE: "created",
        StaffAvailabilityAction.CREATE_PAUSE: "created",
        StaffAvailabilityAction.END_PAUSE: "pause_ended",
        StaffAvailabilityAction.CANCEL: "cancelled",
    }[action]


def _block_payload(block):
    if block is None:
        return None
    return {
        "block_id": block.block_id,
        "staff_id": block.staff_id,
        "kind": block.kind.value,
        "start_date": block.start_date.isoformat(),
        "end_date": block.end_date.isoformat() if block.end_date else None,
        "status": block.status.value,
        "reason": block.reason,
    }


def _require_single_mutation(cursor, error_code):
    if int(cursor.rowcount) != 1:
        raise StaffAvailabilityDomainError(error_code)


def _mapping_rows(rows):
    values = tuple(rows or ())
    if any(not isinstance(row, Mapping) for row in values):
        raise ValueError("staff availability repository returned an invalid row")
    return values


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("staff availability date is invalid")


def _as_optional_date(value):
    return _as_date(value) if value is not None else None


def _database_datetime(value):
    if value.tzinfo is None:
        raise ValueError("staff availability event time must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _canonical_json(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("staff availability receipt snapshot must be an object")
    return payload


_BLOCK_COLUMNS = "id,staff_id,block_kind,start_date,end_date,status,reason"
_BLOCK_RANGE_SQL = (
    f"SELECT {_BLOCK_COLUMNS} FROM scheduling_staff_unavailability_blocks "
    "WHERE staff_id=%s AND start_date<=%s AND (end_date IS NULL OR end_date>=%s) "
    "ORDER BY start_date,id"
)
_BLOCK_ID_SQL = f"SELECT {_BLOCK_COLUMNS} FROM scheduling_staff_unavailability_blocks WHERE id=%s AND staff_id=%s"
_BLOCK_BY_ID_SQL = f"SELECT {_BLOCK_COLUMNS} FROM scheduling_staff_unavailability_blocks WHERE id=%s"
_EFFECTIVE_OVERLAP_SQL = (
    f"SELECT {_BLOCK_COLUMNS} FROM scheduling_staff_unavailability_blocks "
    "WHERE staff_id=%s AND status='effective' AND (end_date IS NULL OR end_date>=%s) "
    "AND (%s IS NULL OR start_date<=%s) ORDER BY start_date,id"
)
_AGGREGATE_ENSURE_SQL = (
    "INSERT INTO scheduling_staff_availability_aggregates(staff_id,aggregate_version) "
    "VALUES (%s,0) ON DUPLICATE KEY UPDATE staff_id=VALUES(staff_id)"
)
_AGGREGATE_SELECT_SQL = (
    "SELECT aggregate_version FROM scheduling_staff_availability_aggregates WHERE staff_id=%s"
)
_VERSION_INCREMENT_SQL = (
    "UPDATE scheduling_staff_availability_aggregates SET aggregate_version=aggregate_version+1 "
    "WHERE staff_id=%s AND aggregate_version=%s"
)
_BLOCK_INSERT_SQL = (
    "INSERT INTO scheduling_staff_unavailability_blocks "
    "(staff_id,block_kind,start_date,end_date,status,reason,created_by,created_at) "
    "VALUES (%s,%s,%s,%s,'effective',%s,%s,%s)"
)
_END_PAUSE_SQL = (
    "UPDATE scheduling_staff_unavailability_blocks SET end_date=%s,ended_by=%s,ended_at=%s "
    "WHERE id=%s AND staff_id=%s AND block_kind='paused_service' "
    "AND status='effective' AND end_date IS NULL"
)
_CANCEL_BLOCK_SQL = (
    "UPDATE scheduling_staff_unavailability_blocks SET status='cancelled',cancelled_by=%s,cancelled_at=%s "
    "WHERE id=%s AND staff_id=%s AND status='effective'"
)
_EVENT_INSERT_SQL = (
    "INSERT INTO scheduling_staff_availability_events "
    "(event_key,staff_id,aggregate_version,block_id,event_type,before_snapshot,after_snapshot,"
    "actor,reason,correlation_id,occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_RECEIPT_SELECT_SQL = (
    "SELECT idempotency_key,request_fingerprint,result_snapshot "
    "FROM scheduling_staff_availability_apply_receipts WHERE idempotency_key=%s"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO scheduling_staff_availability_apply_receipts "
    "(idempotency_key,request_fingerprint,preview_fingerprint,staff_id,aggregate_version,block_id,"
    "action,result_snapshot,actor,reason,correlation_id,created_at) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_ASSIGNMENT_CONFLICT_SQL = (
    "SELECT CAST(a.id AS CHAR) AS source_identity,a.assigned_start_date AS start_date,"
    "a.assigned_end_date AS end_date FROM case_staff_assignments a "
    "JOIN scheduling_generations g ON g.id=a.generation_id "
    "AND g.status='effective' AND g.effective_marker=1 "
    "WHERE a.staff_id=%s AND a.status NOT IN ('cancelled','replaced') AND a.assigned_end_date>=%s "
    "AND (%s IS NULL OR a.assigned_start_date<=%s) ORDER BY a.assigned_start_date,a.id"
)
_WAITING_LOCK_CONFLICT_SQL = (
    "SELECT CONCAT(d.lock_id,':',d.segment_id,':',d.lock_date) AS source_identity,"
    "d.lock_date AS start_date,d.lock_date AS end_date FROM caregiver_availability_lock_days d "
    "JOIN caregiver_availability_locks h ON h.id=d.lock_id "
    "WHERE d.staff_id=%s AND d.active_marker=1 AND h.status='active' AND h.is_active=1 "
    "AND d.lock_date>=%s AND (%s IS NULL OR d.lock_date<=%s) ORDER BY d.lock_date,d.id"
)
_BUFFER_CONFLICT_SQL = (
    "SELECT CONCAT(assignment_id,':',buffer_date) AS source_identity,"
    "buffer_date AS start_date,buffer_date AS end_date FROM scheduling_buffer_days "
    "WHERE staff_id=%s AND status='active' AND active_marker=1 AND buffer_date>=%s "
    "AND (%s IS NULL OR buffer_date<=%s) ORDER BY buffer_date,id"
)
_WAITING_BUFFER_CONFLICT_SQL = (
    "SELECT CONCAT(s.id,':waiting-buffer') AS source_identity,"
    "DATE_ADD(s.assigned_end_date,INTERVAL 1 DAY) AS start_date,"
    "DATE_ADD(s.assigned_end_date,INTERVAL 7 DAY) AS end_date "
    "FROM caregiver_matching_plan_segments s "
    "JOIN caregiver_availability_locks h ON h.plan_id=s.plan_id "
    "WHERE s.staff_id=%s AND h.status='active' AND h.is_active=1 "
    "AND DATE_ADD(s.assigned_end_date,INTERVAL 7 DAY)>=%s "
    "AND (%s IS NULL OR DATE_ADD(s.assigned_end_date,INTERVAL 1 DAY)<=%s) "
    "ORDER BY s.assigned_end_date,s.id"
)
_CONFLICT_QUERIES = (
    ("assignment", _ASSIGNMENT_CONFLICT_SQL),
    ("waiting_lock", _WAITING_LOCK_CONFLICT_SQL),
    ("buffer", _BUFFER_CONFLICT_SQL),
    ("buffer", _WAITING_BUFFER_CONFLICT_SQL),
)


__all__ = ["MySqlStaffAvailabilityRepository"]
