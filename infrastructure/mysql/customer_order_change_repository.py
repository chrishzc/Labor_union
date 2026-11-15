"""Order-change request storage and the customer-bound intake query."""

from __future__ import annotations

import json
from datetime import timezone
from typing import Any

from domains.orders.order_change_request import (
    CustomerOrderChangeError,
    CustomerOrderChangeKind,
    NewOrderChangeRequest,
    OrderChangeCompletion,
    OrderChangeRequest,
)
from subsystems.line.customer_order_change_contracts import CustomerOrderSnapshot
from subsystems.orders.order_change_requests import LegacyOrderChangeReference


class MySqlCustomerOrderChangeRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_for_client(self, client_id: int) -> tuple[CustomerOrderSnapshot, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_SELECT + " WHERE o.client_id=%s ORDER BY o.created_at DESC,o.case_no DESC", (client_id,))
            return tuple(_snapshot(row) for row in cursor.fetchall() or ())

    def load_for_client(
        self, client_id: int, case_no: str, *, lock: bool = False
    ) -> CustomerOrderSnapshot | None:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                _ORDER_SELECT + " WHERE o.client_id=%s AND o.case_no=%s" + suffix,
                (client_id, case_no),
            )
            row = cursor.fetchone()
        return _snapshot(row) if row else None

    def find_submission(self, client_id: int, idempotency_digest: str) -> OrderChangeRequest | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _REQUEST_SELECT + " WHERE client_id=%s AND idempotency_digest=%s",
                (client_id, idempotency_digest),
            )
            row = cursor.fetchone()
        return _request(row) if row else None

    def create_request(self, command: NewOrderChangeRequest) -> OrderChangeRequest:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO order_change_requests "
                "(case_no, client_id, kind, before_payload, requested_payload, idempotency_digest, command_fingerprint, submitted_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (
                    command.case_no, command.client_id, command.kind.value,
                    json.dumps(dict(command.before), ensure_ascii=False),
                    json.dumps(dict(command.requested), ensure_ascii=False),
                    command.idempotency_digest, command.command_fingerprint,
                ),
            )
            request_id = int(cursor.lastrowid)
        return self._readback(request_id)

    def list_requests(
        self, *, case_no: str | None, pending_only: bool, before_id: int | None, limit: int
    ) -> tuple[OrderChangeRequest, ...]:
        predicates = []
        parameters: list[str | int] = []
        if case_no is not None:
            predicates.append("case_no=%s")
            parameters.append(case_no)
        if pending_only:
            predicates.append("completed_at IS NULL")
        if before_id is not None:
            predicates.append("id<%s")
            parameters.append(before_id)
        where = " WHERE " + " AND ".join(predicates) if predicates else ""
        parameters.append(limit)
        with self._connection.cursor() as cursor:
            cursor.execute(_REQUEST_SELECT + where + " ORDER BY id DESC LIMIT %s", tuple(parameters))
            return tuple(_request(row) for row in cursor.fetchall() or ())

    def load_request(self, request_id: int, *, lock: bool = False) -> OrderChangeRequest | None:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_REQUEST_SELECT + " WHERE id=%s" + suffix, (request_id,))
            row = cursor.fetchone()
        return _request(row) if row else None

    def complete_request(
        self, request_id: int, *, result: str, actor_id: int, actor_name: str
    ) -> OrderChangeRequest:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE order_change_requests "
                "SET result=%s, completed_by=%s, completed_by_name=%s, completed_at=UTC_TIMESTAMP(6) "
                "WHERE id=%s AND completed_at IS NULL",
                (result, actor_id, actor_name, request_id),
            )
            if cursor.rowcount != 1:
                raise CustomerOrderChangeError("order_change_request_version_stale")
        return self._readback(request_id)

    def list_legacy_requests(
        self, case_no: str, *, before_event_id: int | None, limit: int
    ) -> tuple[LegacyOrderChangeReference, ...]:
        # The event prefix and exact server-written header belong to the old structured form.
        # A ticket can also contain applications for other cases.
        header = f"[訂單異動申請]\n案件：{case_no}\n項目："
        pagination = " AND e.id<%s" if before_event_id is not None else ""
        parameters = (header, header, before_event_id, limit) if before_event_id is not None else (header, header, limit)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT e.id AS event_id,t.id AS ticket_id,t.status,e.created_at_utc "
                "FROM customer_service_ticket_events e "
                "JOIN customer_service_tickets t ON t.id=e.ticket_id "
                "WHERE e.event_key LIKE 'line-order-change:%%' AND e.event_type='customer_message' "
                "AND CAST(LEFT(e.message_text, CHAR_LENGTH(%s)) AS BINARY)=CAST(%s AS BINARY)"
                + pagination + " ORDER BY e.id DESC LIMIT %s",
                parameters,
            )
            return tuple(LegacyOrderChangeReference(
                int(row["event_id"]), int(row["ticket_id"]), row["status"],
                row["created_at_utc"].replace(tzinfo=timezone.utc),
            ) for row in cursor.fetchall() or ())

    def _readback(self, request_id: int) -> OrderChangeRequest:
        request = self.load_request(request_id)
        if request is None:
            raise CustomerOrderChangeError("order_change_write_readback_missing")
        return request


def _request(row: dict[str, Any]) -> OrderChangeRequest:
    completion = None
    if row["completed_at"] is not None:
        completion = OrderChangeCompletion(
            row["result"], int(row["completed_by"]), row["completed_by_name"],
            row["completed_at"].replace(tzinfo=timezone.utc),
        )
    return OrderChangeRequest(
        int(row["id"]), row["case_no"], CustomerOrderChangeKind(row["kind"]),
        json.loads(row["before_payload"]), json.loads(row["requested_payload"]),
        row["submitted_at"].replace(tzinfo=timezone.utc), row["command_fingerprint"], completion,
    )


def _snapshot(row: dict[str, Any]) -> CustomerOrderSnapshot:
    cooking = row.get("requires_cooking")
    values = {
        "service_city": str(row.get("service_city") or ""),
        "service_address": str(row.get("service_address") or ""),
        "residence_type": str(row.get("residence_type") or ""),
        "requires_cooking": "未設定" if cooking is None else "需要" if bool(cooking) else "不需要",
        "start_date": str(row.get("start_date") or ""),
        "end_date": str(row.get("end_date") or ""),
        "service_days": str(row.get("service_days") or ""),
        "service_start_time": str(row.get("service_start_time") or ""),
        "service_end_time": str(row.get("service_end_time") or ""),
        "service_end_day_offset": str(row.get("service_end_day_offset") or "0"),
    }
    return CustomerOrderSnapshot(
        str(row["case_no"]),
        str(row["status"]),
        int(row.get("order_version") or 0),
        int(row.get("client_profile_version") or 0),
        values,
    )


_ORDER_SELECT = (
    "SELECT o.case_no,o.status,o.lifecycle_version AS order_version,"
    "o.start_date,o.end_date,o.service_days,o.service_start_time,o.service_end_time,"
    "o.service_end_day_offset,o.requires_cooking,c.city AS service_city,"
    "c.address AS service_address,c.residence_type,"
    "c.client_profile_version "
    "FROM orders o JOIN clients c ON c.id=o.client_id"
)

_REQUEST_SELECT = (
    "SELECT id,case_no,kind,before_payload,requested_payload,submitted_at,command_fingerprint,"
    "result,completed_by,completed_by_name,completed_at FROM order_change_requests"
)

__all__ = ["MySqlCustomerOrderChangeRepository"]
