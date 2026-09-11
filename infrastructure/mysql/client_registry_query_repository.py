"""MySQL read adapter for the case-centered client registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


_CLIENT_FIELDS = (
    "name", "gender", "phone", "city", "address", "residence_type",
    "delivery_type", "baby_info", "notes",
)
_BECLASS_FIELDS = (
    "name", "email", "phone", "tel", "ext", "city", "zip_code", "address", "admin_notes",
)


class MySqlClientRegistryQueryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_page(self, *, query: str | None, limit: int, after: str | None):
        where = ["o.case_no IS NOT NULL"]
        parameters: list[object] = []
        if after is not None:
            where.append("o.case_no > %s")
            parameters.append(after)
        if query is not None:
            where.append("CONCAT_WS(' ',o.case_no,COALESCE(c.name,''),COALESCE(c.phone,'')) LIKE %s")
            parameters.append(f"%{query}%")
        parameters.append(limit + 1)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS client_id,o.case_no,c.name,c.phone,c.city,"
                "o.start_date AS planned_start_date,o.status AS order_status "
                "FROM orders o JOIN clients c ON c.id=o.client_id WHERE "
                + " AND ".join(where)
                + " ORDER BY o.case_no ASC LIMIT %s",
                tuple(parameters),
            )
            rows = tuple(cursor.fetchall() or ())
        visible = rows[:limit]
        next_cursor = str(visible[-1]["case_no"]) if len(rows) > limit and visible else None
        return visible, next_cursor

    def load_detail(self, case_no: str) -> Mapping[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS client_id,o.case_no,c.client_profile_version,"
                + ",".join(f"c.{field}" for field in _CLIENT_FIELDS)
                + " FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s LIMIT 1",
                (case_no,),
            )
            client = cursor.fetchone()
            if client is None:
                return None
            cursor.execute(
                "SELECT id AS beclass_record_id," + ",".join(_BECLASS_FIELDS)
                + " FROM beclass_records WHERE bound_case_no=%s ORDER BY id LIMIT 2",
                (case_no,),
            )
            beclass_rows = tuple(cursor.fetchall() or ())
            state = None
            if len(beclass_rows) == 1:
                cursor.execute(
                    "SELECT aggregate_version,effective_values_json "
                    "FROM beclass_record_correction_states WHERE beclass_record_id=%s",
                    (int(beclass_rows[0]["beclass_record_id"]),),
                )
                state = cursor.fetchone()
        if not beclass_rows:
            beclass_status = "unbound"
            beclass_record_id = None
            beclass_values = None
        elif len(beclass_rows) > 1:
            beclass_status = "duplicate_binding"
            beclass_record_id = None
            beclass_values = None
        else:
            beclass_status = "ready"
            source = beclass_rows[0]
            beclass_record_id = int(source["beclass_record_id"])
            beclass_values = {field: source.get(field) for field in _BECLASS_FIELDS}
            beclass_values.update(_decode((state or {}).get("effective_values_json")))
        return {
            "case_no": str(client["case_no"]),
            "client_id": int(client["client_id"]),
            "client_profile_version": int(client.get("client_profile_version") or 0),
            "client_values": {field: client.get(field) for field in _CLIENT_FIELDS},
            "beclass_status": beclass_status,
            "beclass_record_id": beclass_record_id,
            "beclass_version": int((state or {}).get("aggregate_version") or 0),
            "beclass_values": beclass_values,
        }


def _decode(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


__all__ = ["MySqlClientRegistryQueryRepository"]
