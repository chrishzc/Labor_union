"""
File: service_day_checkpoint_repository.py
Description: 以正式排班和訂單服務時段形成每日服務結束 checkpoint，並同交易寫入 Scheduling outbox。
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from pymysql.err import IntegrityError

from domains.orders.terms import ServiceTimeTerms
from subsystems.scheduling.service_day_checkpoint_workflow import ServiceDayCheckpointCandidate


class MySqlServiceDayCheckpointRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def due_candidates(self, now: datetime, limit: int) -> tuple[ServiceDayCheckpointCandidate, ...]:
        if now.tzinfo is None:
            raise ValueError("service day checkpoint now must be timezone-aware")
        with self._connection.cursor() as cursor:
            cursor.execute(_DUE_SCHEDULES_SQL, (now.astimezone(_TAIPEI).date(), limit))
            rows = tuple(cursor.fetchall() or ())
        result = []
        for row in rows:
            candidate = _candidate(row)
            if candidate is not None and candidate.service_ends_at_utc <= now.astimezone(UTC):
                result.append(candidate)
        return tuple(result)

    def append_checkpoint(self, candidate: ServiceDayCheckpointCandidate) -> bool:
        key = f"scheduling-service-day-checkpoint:{candidate.assignment_id}:{candidate.service_date}"
        try:
            with self._connection.cursor() as cursor:
                baby_log_completed = _baby_log_completed(
                    cursor, candidate.assignment_id, candidate.service_date
                )
                cursor.execute(
                    _CHECKPOINT_INSERT_SQL,
                    (
                        candidate.case_no,
                        candidate.assignment_id,
                        candidate.schedule_id,
                        candidate.staff_id,
                        candidate.service_date,
                        candidate.service_ends_at_utc,
                        candidate.requires_cooking,
                        baby_log_completed,
                        key,
                    ),
                )
                checkpoint_id = int(cursor.lastrowid)
                cursor.execute(
                    _CHECKPOINT_EVENT_INSERT_SQL,
                    (checkpoint_id, key),
                )
                event_id = int(cursor.lastrowid)
                payload = json.dumps(
                    {
                        "assignment_id": candidate.assignment_id,
                        "baby_log_completed": baby_log_completed,
                        "case_no": candidate.case_no,
                        "requires_cooking": candidate.requires_cooking,
                        "service_date": candidate.service_date,
                        "service_ends_at_utc": candidate.service_ends_at_utc.isoformat(),
                        "staff_id": candidate.staff_id,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                cursor.execute(_CHECKPOINT_OUTBOX_INSERT_SQL, (event_id, key, payload))
        except IntegrityError as error:
            if getattr(error, "args", [None])[0] == 1062:
                return False
            raise
        return True


def _candidate(row) -> ServiceDayCheckpointCandidate | None:
    required = ("id", "assignment_id", "case_no", "staff_id", "work_date", "service_start_time", "service_end_time", "service_end_day_offset", "requires_cooking")
    if any(row.get(key) is None for key in required):
        return None
    work_date = _date(row["work_date"])
    start_time = _time(row["service_start_time"])
    end_time = _time(row["service_end_time"])
    if work_date is None or start_time is None or end_time is None or row["requires_cooking"] is None:
        return None
    try:
        end_offset = int(row["service_end_day_offset"])
        completion = ServiceTimeTerms(start_time, end_time, end_offset).completion_instant(work_date).astimezone(UTC)
    except (TypeError, ValueError):
        return None
    return ServiceDayCheckpointCandidate(
        assignment_id=int(row["assignment_id"]),
        schedule_id=int(row["id"]),
        case_no=str(row["case_no"]),
        staff_id=int(row["staff_id"]),
        service_date=work_date.isoformat(),
        service_ends_at_utc=completion,
        requires_cooking=bool(row["requires_cooking"]),
    )


def _date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _time(value) -> time | None:
    return value if isinstance(value, time) else None


def _baby_log_completed(cursor, assignment_id: int, service_date: str) -> bool:
    cursor.execute(_LOG_EXISTS_SQL, (assignment_id, service_date))
    return cursor.fetchone() is not None


_DUE_SCHEDULES_SQL = (
    "SELECT ss.id,ss.assignment_id,csa.case_no,csa.staff_id,ss.work_date,"
    "o.service_start_time,o.service_end_time,o.service_end_day_offset,o.requires_cooking "
    "FROM staff_schedule ss JOIN case_staff_assignments csa ON csa.id=ss.assignment_id "
    "JOIN orders o ON o.case_no=csa.case_no "
    "LEFT JOIN scheduling_service_day_checkpoints checkpoint "
    "ON checkpoint.assignment_id=ss.assignment_id AND checkpoint.service_date=ss.work_date "
    "WHERE ss.is_work_day=1 AND (csa.status IS NULL OR csa.status<>'cancelled') "
    "AND ss.work_date<=%s AND checkpoint.id IS NULL ORDER BY ss.work_date,ss.id LIMIT %s FOR UPDATE"
)
_CHECKPOINT_INSERT_SQL = (
    "INSERT INTO scheduling_service_day_checkpoints "
    "(case_no,assignment_id,schedule_id,staff_id,service_date,service_ends_at_utc,requires_cooking,baby_log_completed,checkpoint_key) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_CHECKPOINT_EVENT_INSERT_SQL = (
    "INSERT INTO scheduling_service_day_checkpoint_events (checkpoint_id,event_type,idempotency_key) "
    "VALUES (%s,'service_ended',%s)"
)
_CHECKPOINT_OUTBOX_INSERT_SQL = (
    "INSERT INTO scheduling_service_day_checkpoint_outbox (event_id,intent_key,payload_snapshot) VALUES (%s,%s,%s)"
)
_LOG_EXISTS_SQL = (
    "SELECT id FROM scheduling_service_day_logs WHERE assignment_id=%s AND service_date=%s FOR UPDATE"
)
_TAIPEI = ZoneInfo("Asia/Taipei")


__all__ = ["MySqlServiceDayCheckpointRepository"]
