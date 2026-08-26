"""
File: service_day_log_repository.py
Description: 以正式指派與已保存 LINE media 驗證月嫂服務日日誌，並同交易寫入 Scheduling event/outbox。
"""

from __future__ import annotations

import json

from subsystems.scheduling.service_day_log_workflow import ApplyServiceDayLog, ServiceDayLogResult


class MySqlServiceDayLogRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

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
            payload = json.dumps({"case_no": assignment["case_no"], "assignment_id": command.assignment_id, "service_date": command.intent.service_date.isoformat(), "requires_cooking": assignment["requires_cooking"]}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            cursor.execute(_OUTBOX_INSERT_SQL, (event_id, f"scheduling-service-day-log:{log_id}", payload))
        return ServiceDayLogResult(
            log_id,
            str(assignment["case_no"]),
            command.assignment_id,
            command.intent.service_date.isoformat(),
            command.intent.baby_log_text.strip(),
            bool(assignment["requires_cooking"]),
            "created",
        )

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
        return _result_from_row(row, outcome="existing")

    def load_for_staff(
        self, log_id: int, staff_id: int, line_user_id: str
    ) -> ServiceDayLogResult | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_READBACK_SQL, (log_id, staff_id, line_user_id))
            row = cursor.fetchone()
        if not isinstance(row, dict):
            return None
        return _result_from_row(row, outcome="existing")


def _result_from_row(row, *, outcome: str) -> ServiceDayLogResult:
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
_LOG_INSERT_SQL = (
    "INSERT INTO scheduling_service_day_logs (case_no,assignment_id,staff_id,staff_line_user_id,service_date,baby_log_text,requires_cooking,content_fingerprint,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_EVENT_INSERT_SQL = "INSERT INTO scheduling_service_day_log_events (service_day_log_id,assignment_id,staff_id,service_date,event_type,idempotency_key) VALUES (%s,%s,%s,%s,'submitted',%s)"
_OUTBOX_INSERT_SQL = "INSERT INTO scheduling_service_day_log_outbox (event_id,intent_key,payload_snapshot) VALUES (%s,%s,%s)"


__all__ = ["MySqlServiceDayLogRepository"]
