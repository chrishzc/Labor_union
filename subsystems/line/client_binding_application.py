"""Typed transaction owner for an existing client's LINE binding request."""

from __future__ import annotations

import pymysql

from subsystems.line.identity_review_workflow import (
    complete_client_binding_in_transaction,
    submit_client_rebind_request_in_transaction,
)


def bind_client(connection, *, name: str, phone: str, line_user_id: str, force_rebind: bool) -> dict:
    """Return a typed binding outcome without allowing the route to own writes."""
    normalized_phone = phone.replace(" ", "").replace("-", "")
    try:
        begin = getattr(connection, "begin", None)
        if callable(begin):
            begin()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            client = _find_client(cursor, name, normalized_phone)
            if client is None:
                connection.rollback()
                return {"kind": "not_found"}
            result = _apply_binding(cursor, client, line_user_id, force_rebind)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise


def _find_client(cursor, name: str, phone: str):
    cursor.execute(
        """SELECT id,name,case_no,line_user_id FROM clients
           WHERE name=%s AND REPLACE(REPLACE(phone,'-',''),' ','')=%s
           ORDER BY id DESC LIMIT 1""",
        (name, phone),
    )
    return cursor.fetchone()


def _apply_binding(cursor, client: dict, line_user_id: str, force_rebind: bool) -> dict:
    current = str(client.get("line_user_id") or "").strip()
    if current and current != line_user_id:
        if not force_rebind:
            return {"kind": "confirm_rebind"}
        request = submit_client_rebind_request_in_transaction(
            cursor, client_id=client["id"], client_name=client["name"],
            old_line_user_id=current, new_line_user_id=line_user_id,
        )
        return {"kind": "pending_approval", "request_id": request["request_id"]}
    result = complete_client_binding_in_transaction(
        cursor, client_id=client["id"], client_name=client["name"],
        case_no=client["case_no"], current_line_user_id=current, line_user_id=line_user_id,
    )
    return {"kind": "bound", "client": client, **result}


__all__ = ["bind_client"]
