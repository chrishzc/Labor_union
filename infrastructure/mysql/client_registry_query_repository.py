"""MySQL read adapter for the case-centered client registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from domains.case_import.order_information import project_order_information
from subsystems.case_import.beclass_correction_workflow import allows_manual_beclass_source


_CLIENT_FIELDS = (
    "name", "gender", "phone", "city", "address", "residence_type",
    "delivery_type", "baby_info", "notes",
)
_BECLASS_FIELDS = (
    "name", "email", "phone", "tel", "ext", "city", "zip_code", "address", "admin_notes",
)
_SORT_COLUMNS = {
    "case_no": "o.case_no",
    "customer_name": "c.name",
    "service_days": "o.service_days",
    "expected_start_date": "o.start_date",
}


class MySqlClientRegistryQueryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_page(
        self,
        *,
        query: str | None,
        multi_birth_count: str | None,
        order_status: str | None,
        requires_cooking: bool | None,
        sort_by: str | None,
        sort_order: str | None,
        limit: int,
        after: str | None,
    ):
        where = ["o.case_no IS NOT NULL"]
        parameters: list[object] = []
        if after is not None:
            where.append("o.case_no > %s")
            parameters.append(after)
        if query is not None:
            where.append("CONCAT_WS(' ',o.case_no,COALESCE(c.name,''),COALESCE(c.phone,'')) LIKE %s")
            parameters.append(f"%{query}%")
        birth_count_sql = (
            "COALESCE("
            "CASE WHEN JSON_VALID(bcs.effective_values_json) THEN "
            "JSON_UNQUOTE(JSON_EXTRACT(bcs.effective_values_json, '$.multi_birth_count')) END,"
            "CASE WHEN JSON_VALID(br.survey_details) THEN "
            "JSON_UNQUOTE(JSON_EXTRACT(br.survey_details, '$.\"特殊計費:胎數\"')) END)"
        )
        if multi_birth_count is not None:
            where.append(f"{birth_count_sql} = %s")
            parameters.append(multi_birth_count)
        if order_status is not None:
            where.append("o.status = %s")
            parameters.append(order_status)
        if requires_cooking is not None:
            where.append("o.requires_cooking = %s")
            parameters.append(requires_cooking)
        if sort_by is None:
            order_by = "o.case_no ASC"
        else:
            column = _SORT_COLUMNS[sort_by]
            direction = "DESC" if sort_order == "desc" else "ASC"
            order_by = f"{column} {direction}"
            if column != "o.case_no":
                order_by += ", o.case_no ASC"
        parameters.append(limit + 1)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS client_id,o.case_no,c.name,c.phone,c.city,"
                + birth_count_sql + " AS multi_birth_count,"
                "o.service_days,o.requires_cooking,"
                "o.start_date AS planned_start_date,o.status AS order_status "
                "FROM orders o JOIN clients c ON c.id=o.client_id "
                "LEFT JOIN (SELECT bound_case_no,MAX(id) AS id,MAX(survey_details) AS survey_details "
                "FROM beclass_records WHERE bound_case_no IS NOT NULL GROUP BY bound_case_no HAVING COUNT(*)=1) br "
                "ON br.bound_case_no=o.case_no "
                "LEFT JOIN beclass_record_correction_states bcs ON bcs.beclass_record_id=br.id WHERE "
                + " AND ".join(where)
                + " ORDER BY " + order_by + " LIMIT %s",
                tuple(parameters),
            )
            rows = tuple(cursor.fetchall() or ())
        visible = rows[:limit]
        next_cursor = str(visible[-1]["case_no"]) if len(rows) > limit and visible else None
        return visible, next_cursor

    def load_detail(self, case_no: str) -> Mapping[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS client_id,o.case_no,o.status AS order_status,c.client_profile_version,"
                + ",".join(f"c.{field}" for field in _CLIENT_FIELDS)
                + " FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s LIMIT 1",
                (case_no,),
            )
            client = cursor.fetchone()
            if client is None:
                return None
            cursor.execute(
                "SELECT id AS beclass_record_id,record_origin,survey_details," + ",".join(_BECLASS_FIELDS)
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
        effective_values: dict[str, Any] = {}
        if not beclass_rows and allows_manual_beclass_source(client.get("order_status")):
            beclass_status = "ready"
            beclass_record_id = None
            beclass_source_kind = "admin_manual"
            beclass_values = {field: None for field in _BECLASS_FIELDS}
        elif not beclass_rows:
            beclass_status = "unbound"
            beclass_record_id = None
            beclass_source_kind = None
            beclass_values = None
        elif len(beclass_rows) > 1:
            beclass_status = "duplicate_binding"
            beclass_record_id = None
            beclass_source_kind = None
            beclass_values = None
        else:
            beclass_status = "ready"
            source = beclass_rows[0]
            beclass_record_id = int(source["beclass_record_id"])
            beclass_source_kind = str(source.get("record_origin") or "imported")
            effective_values = _decode((state or {}).get("effective_values_json"))
            beclass_values = {field: source.get(field) for field in _BECLASS_FIELDS}
            beclass_values.update({
                field: effective_values[field]
                for field in _BECLASS_FIELDS
                if field in effective_values
            })
        if beclass_status == "ready":
            order_information = project_order_information(
                beclass_rows[0].get("survey_details") if beclass_rows else None
            )
            order_information_values = dict(order_information.values)
            order_information_issues = (
                {} if beclass_source_kind == "admin_manual"
                else dict(order_information.issues)
            )
            if "multi_birth_count" in effective_values:
                order_information_values["multi_birth_count"] = effective_values["multi_birth_count"]
                order_information_issues.pop("multi_birth_count", None)
            beclass_values["multi_birth_count"] = order_information_values.get("multi_birth_count")
        else:
            order_information_values = None
            order_information_issues = {}
        return {
            "case_no": str(client["case_no"]),
            "client_id": int(client["client_id"]),
            "client_profile_version": int(client.get("client_profile_version") or 0),
            "client_values": {field: client.get(field) for field in _CLIENT_FIELDS},
            "beclass_status": beclass_status,
            "beclass_record_id": beclass_record_id,
            "beclass_source_kind": beclass_source_kind,
            "beclass_version": int((state or {}).get("aggregate_version") or 0),
            "beclass_values": beclass_values,
            "order_information_values": order_information_values,
            "order_information_issues": order_information_issues,
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
