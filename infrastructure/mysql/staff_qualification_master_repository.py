"""
File: staff_qualification_master_repository.py
Description: 以固定唯讀 SQL 提供 Staff qualification master 的來源事實。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Mapping

from pymysql.err import ProgrammingError

from subsystems.staff.qualification_master_query import (
    StaffQualificationMasterQuery,
    StaffQualificationNotFound,
    StaffQualificationSourceRecord,
    UnavailabilitySourceRecord,
)


class MySqlStaffQualificationMasterRepository:
    """不 commit、不寫入，只讀選定 Staff 的資格與 availability 根事實。"""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch(self, query: StaffQualificationMasterQuery) -> StaffQualificationSourceRecord:
        with self._connection.cursor() as cursor:
            cursor.execute(_STAFF_SQL, (query.staff_id,))
            staff_row = cursor.fetchone()
            if staff_row is None:
                raise StaffQualificationNotFound(f"staff:{query.staff_id}")

            cursor.execute(_COOKING_SQL, (query.staff_id,))
            cooking_rows = tuple(cursor.fetchall() or ())
            unavailability_available, unavailability_reason, blocks = _load_unavailability(
                cursor,
                query,
            )

        return StaffQualificationSourceRecord(
            staff_id=int(staff_row["id"]),
            staff_name=_required_text(staff_row, "name", 100),
            staff_source_version=_source_version(staff_row.get("updated_at")),
            special_skills=_parse_special_skills(staff_row.get("special_skills")),
            cooking_skills=tuple(
                (
                    _required_text(row, "skill_name", 50),
                    _optional_text(row, "custom_skill_detail", 100),
                )
                for row in cooking_rows
            ),
            massage_certified=_optional_bool(staff_row.get("has_massage_cert")),
            unavailability_source_available=unavailability_available,
            unavailability_source_reason=unavailability_reason,
            unavailability_blocks=blocks,
        )


def _load_unavailability(cursor: Any, query: StaffQualificationMasterQuery):
    try:
        cursor.execute(
            _UNAVAILABILITY_SQL,
            (query.staff_id, query.as_of, query.as_of),
        )
    except ProgrammingError as error:
        if _mysql_code(error) == 1146:
            return False, "staff_unavailability_schema_not_ready", ()
        raise
    rows = tuple(cursor.fetchall() or ())
    return True, "scheduling_staff_unavailability_ready", tuple(
        UnavailabilitySourceRecord(
            block_id=int(row["id"]),
            kind=_required_text(row, "block_kind", 32),
            start_date=_as_date(row["start_date"]),
            end_date=_optional_date(row.get("end_date")),
            source_version=_source_version(row.get("created_at")),
        )
        for row in rows
    )


def _parse_special_skills(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("staff special_skills JSON is invalid") from error
    if not isinstance(value, list):
        raise ValueError("staff special_skills must be a JSON array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("staff special_skills contains an invalid value")
        text = item.strip()
        if text not in result:
            result.append(text)
    return tuple(result)


def _required_text(row: Mapping[str, object], field: str, maximum: int) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"staff qualification {field} is invalid")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"staff qualification {field} is too long")
    return value


def _optional_text(row: Mapping[str, object], field: str, maximum: int) -> str | None:
    value = row.get(field)
    if value is None:
        return None
    return _required_text(row, field, maximum)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValueError("staff qualification certificate value is invalid")


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("staff qualification date is invalid")


def _optional_date(value: object) -> date | None:
    return None if value is None else _as_date(value)


def _source_version(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError("staff qualification source version is invalid")


def _mysql_code(error: BaseException) -> int:
    args = getattr(error, "args", ())
    if not args:
        return 0
    try:
        return int(args[0])
    except (TypeError, ValueError):
        return 0


_STAFF_SQL = (
    "SELECT id,name,has_massage_cert,special_skills,updated_at "
    "FROM staff WHERE id=%s LIMIT 1"
)
_COOKING_SQL = (
    "SELECT skill_name,custom_skill_detail FROM staff_cooking_skills "
    "WHERE staff_id=%s ORDER BY skill_name"
)
_UNAVAILABILITY_SQL = (
    "SELECT id,block_kind,start_date,end_date,created_at "
    "FROM scheduling_staff_unavailability_blocks "
    "WHERE staff_id=%s AND status='effective' AND start_date<=%s "
    "AND (end_date IS NULL OR end_date>=%s) ORDER BY start_date,id"
)


__all__ = ["MySqlStaffQualificationMasterRepository"]
