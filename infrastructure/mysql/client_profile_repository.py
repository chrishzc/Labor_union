"""MySQL adapter for the Client-owned profile change workflow."""

from __future__ import annotations

import json
from typing import Any, Mapping


class MySqlClientProfileRepository:
    """Keep Client root writes behind one typed repository boundary."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_profile(self, client_id: int, *, for_update: bool = False) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id AS client_id,client_profile_version,name,gender,phone,city,address,"
                "residence_type,delivery_type,baby_info,notes FROM clients WHERE id=%s" + suffix,
                (client_id,),
            )
            return cursor.fetchone()

    def load_request(self, request_id: int, *, for_update: bool = False) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id AS request_id,line_user_id,client_id,status,request_version,"
                "client_profile_version AS profile_version,old_values_json AS before_values,"
                "requested_changes_json AS requested_values,reason,created_at,reviewed_at "
                "FROM client_profile_change_requests WHERE id=%s" + suffix,
                (request_id,),
            )
            row = cursor.fetchone()
        return _decode_request(row)

    def list_requests(self, *, status: str | None, page: int, page_size: int) -> tuple[tuple[dict[str, Any], ...], int]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if status:
            clauses.append("status=%s")
            parameters.append(status)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        offset = (page - 1) * page_size
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM client_profile_change_requests" + where, tuple(parameters))
            total = int((cursor.fetchone() or {}).get("total") or 0)
            cursor.execute(
                "SELECT id AS request_id,line_user_id,client_id,status,request_version,"
                "client_profile_version AS profile_version,old_values_json AS before_values,"
                "requested_changes_json AS requested_values,reason,created_at,reviewed_at "
                "FROM client_profile_change_requests" + where + " ORDER BY id DESC LIMIT %s OFFSET %s",
                (*parameters, page_size, offset),
            )
            rows = tuple(_decode_request(row) for row in cursor.fetchall() or ())
        return rows, total

    def find_receipt(self, key: str, *, for_update: bool = False) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT idempotency_key,command_fingerprint,preview_fingerprint,result_json "
                "FROM client_profile_change_apply_receipts WHERE idempotency_key=%s" + suffix,
                (key,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        result = _decode_json(row.get("result_json"), {})
        return {**row, "result": result}

    def create_request(self, *, line_user_id: str, client_id: int, expected_version: int, before: Mapping[str, str], requested: Mapping[str, str], reason: str, idempotency_key: str, correlation_id: str, preview_fingerprint: str, command_fingerprint: str) -> dict[str, Any]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO client_profile_change_requests "
                "(line_user_id,client_id,status,request_version,client_profile_version,"
                "requested_changes_json,old_values_json,reason,idempotency_key,"
                "preview_fingerprint,command_fingerprint,correlation_id) "
                "VALUES (%s,%s,'pending',0,%s,%s,%s,%s,%s,%s,%s,%s)",
                (line_user_id, client_id, expected_version, _json(requested), _json(before), reason,
                 idempotency_key, preview_fingerprint, command_fingerprint, correlation_id),
            )
            request_id = int(cursor.lastrowid)
        return self.load_request(request_id)

    def approve_request(self, *, request_id: int, expected_request_version: int, client_id: int, expected_profile_version: int, before: Mapping[str, str], requested: Mapping[str, str], actor_id: str, reason: str, idempotency_key: str, correlation_id: str, preview_fingerprint: str, command_fingerprint: str) -> dict[str, Any]:
        assignments = ",".join(f"{field}=%s" for field in sorted(requested))
        values = [requested[field] for field in sorted(requested)]
        values.extend((expected_profile_version + 1, client_id, expected_profile_version))
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE clients SET " + assignments + ("," if assignments else "") +
                "client_profile_version=%s WHERE id=%s AND client_profile_version=%s",
                tuple(values),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("client_profile_version_stale")
            cursor.execute(
                "UPDATE client_profile_change_requests SET status='approved_applied',"
                "request_version=request_version+1,applied_values_json=%s,"
                "reviewed_by_admin_user_id=%s,reviewed_at=CURRENT_TIMESTAMP,"
                "review_reason=%s WHERE id=%s AND status='pending' AND request_version=%s",
                (_json(requested), _admin_id(actor_id), reason, request_id, expected_request_version),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("client_profile_request_version_stale")
            cursor.execute(
                "INSERT INTO client_profile_change_outbox "
                "(request_id,event_type,idempotency_key,correlation_id,payload_json) "
                "VALUES (%s,'client_profile.approved',%s,%s,%s)",
                (
                    request_id,
                    idempotency_key,
                    correlation_id,
                    _json({
                        "client_id": client_id,
                        "request_id": request_id,
                        "resulting_profile_version": expected_profile_version + 1,
                    }),
                ),
            )
            cursor.execute(
                "INSERT INTO client_profile_change_events "
                "(request_id,client_id,event_type,resulting_profile_version,actor_id,"
                "reason,idempotency_key,correlation_id,before_values_json,after_values_json) "
                "VALUES (%s,%s,'approved_applied',%s,%s,%s,%s,%s,%s,%s)",
                (request_id, client_id, expected_profile_version + 1, actor_id, reason,
                 idempotency_key, correlation_id, _json(before), _json(requested)),
            )
        return self.load_request(request_id)

    def reject_request(self, *, request_id: int, expected_request_version: int, reason: str, actor_id: str, idempotency_key: str, correlation_id: str, preview_fingerprint: str, command_fingerprint: str) -> dict[str, Any]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE client_profile_change_requests SET status='rejected',"
                "request_version=request_version+1,reviewed_by_admin_user_id=%s,"
                "reviewed_at=CURRENT_TIMESTAMP,rejection_reason=%s "
                "WHERE id=%s AND status='pending' AND request_version=%s",
                (_admin_id(actor_id), reason, request_id, expected_request_version),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("client_profile_request_version_stale")
        return self.load_request(request_id)

    def save_receipt(self, *, idempotency_key: str, command_fingerprint: str, preview_fingerprint: str, result: Mapping[str, Any]) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO client_profile_change_apply_receipts "
                "(idempotency_key,command_fingerprint,preview_fingerprint,result_json) "
                "VALUES (%s,%s,%s,%s)",
                (idempotency_key, command_fingerprint, preview_fingerprint, _json(result)),
            )


def _decode_request(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        **row,
        "before": _decode_json(row.get("before_values"), {}),
        "requested": _decode_json(row.get("requested_values"), {}),
    }


def _decode_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return default
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return default
    return decoded


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _admin_id(actor_id: str) -> int | None:
    value = actor_id.removeprefix("admin:")
    return int(value) if value.isdigit() else None
