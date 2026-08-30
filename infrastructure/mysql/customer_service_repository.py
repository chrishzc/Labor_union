"""
File: customer_service_repository.py
Description: 保存客服需求，並僅依 canonical LINE binding 查詢客戶與月嫂身分投影。
"""

from __future__ import annotations

from typing import Any

from domains.customer_service.ticket import (
    CustomerServiceCategory,
    CustomerServiceStatus,
    CustomerServiceTicket,
    CustomerServiceTicketNotFoundError,
    CustomerServiceVersionConflictError,
)
from subsystems.customer_service.contracts import (
    CreateCustomerServiceMessage,
    CustomerServiceListQuery,
)


class MySqlCustomerServiceRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def create_or_append(
        self,
        command: CreateCustomerServiceMessage,
    ) -> CustomerServiceTicket:
        existing_event = self._ticket_for_event(command.event_key)
        if existing_event is not None:
            return existing_event
        ticket = self._active_ticket(command.line_user_id, command.category)
        if ticket is None:
            ticket = self._latest_ticket(command.line_user_id, command.category)
        if ticket is None:
            ticket = self._create_ticket(command)
        self._append_event(ticket.ticket_id, command)
        return self.get(ticket.ticket_id)

    def get_by_event_key(self, event_key: str) -> CustomerServiceTicket | None:
        return self._ticket_for_event(event_key)

    def create_or_append_escalation_ticket(self, command: Any) -> CustomerServiceTicket:
        """Resolve an already-created canonical ticket event without guessing LINE identity.

        M4 receives only an opaque source event identity.  A missing event is therefore
        fail-closed; ticket creation remains owned by the LINE Customer Service flow.
        """

        event_identity = getattr(command, "source_event_identity", None)
        if not isinstance(event_identity, str) or not event_identity.strip():
            raise CustomerServiceTicketNotFoundError("客服 escalation 缺少 canonical ticket event")
        ticket = self.get_by_event_key(event_identity)
        if ticket is None:
            raise CustomerServiceTicketNotFoundError(
                "找不到 escalation source 對應的既有客服需求"
            )
        return ticket

    def start_handling_for_escalation(
        self, ticket_id: int, expected_version: int, actor_id: str
    ) -> CustomerServiceTicket:
        admin_id = _admin_user_id(actor_id)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE customer_service_tickets SET status='handling',"
                "assigned_to_admin_user_id=COALESCE(%s,assigned_to_admin_user_id),"
                "version=version+1 WHERE id=%s AND version=%s AND status='waiting'",
                (admin_id, ticket_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise CustomerServiceVersionConflictError("客服需求已更新或不在等待狀態")
            cursor.execute(
                _EVENT_INSERT_SQL,
                (
                    ticket_id,
                    f"human-escalation:handling:{ticket_id}:{expected_version}",
                    "status_changed",
                    "human_escalation_handling_started",
                    actor_id,
                ),
            )
        return self.get(ticket_id)

    def resolve_for_escalation(
        self,
        ticket_id: int,
        expected_version: int,
        actor_id: str,
        resolution_code: str,
    ) -> CustomerServiceTicket:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE customer_service_tickets SET status='resolved',"
                "resolved_at_utc=UTC_TIMESTAMP(),version=version+1 "
                "WHERE id=%s AND version=%s AND status='handling'",
                (ticket_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise CustomerServiceVersionConflictError("客服需求已更新或不在處理狀態")
            cursor.execute(
                _EVENT_INSERT_SQL,
                (
                    ticket_id,
                    f"human-escalation:resolve:{ticket_id}:{expected_version}",
                    "status_changed",
                    resolution_code,
                    actor_id,
                ),
            )
        return self.get(ticket_id)

    def get(self, ticket_id: int, *, lock: bool = False) -> CustomerServiceTicket:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_TICKET_SELECT + " WHERE t.id=%s" + suffix, (ticket_id,))
            row = cursor.fetchone()
        if not row:
            raise CustomerServiceTicketNotFoundError(f"找不到客服需求 #{ticket_id}")
        return _ticket(row)

    def detail(self, ticket_id: int) -> dict[str, Any]:
        ticket = self.get(ticket_id)
        with self._connection.cursor() as cursor:
            cursor.execute(_EVENT_LIST_SQL, (ticket_id,))
            events = list(cursor.fetchall() or ())
        return {"ticket": _ticket_view(ticket), "events": events}

    def summary(self) -> dict[str, int]:
        with self._connection.cursor() as cursor:
            cursor.execute(_SUMMARY_SQL)
            row = cursor.fetchone() or {}
        return {key: int(row.get(key) or 0) for key in ("waiting", "handling", "resolved_today")}

    def list(self, query: CustomerServiceListQuery) -> dict[str, Any]:
        clauses, parameters = _list_filters(query)
        offset = (query.page - 1) * query.page_size
        where = " AND ".join(clauses)
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total "
                f"FROM customer_service_tickets t WHERE {where}",
                parameters,
            )
            total = int((cursor.fetchone() or {}).get("total") or 0)
            cursor.execute(
                _TICKET_SELECT
                + f" WHERE {where} ORDER BY t.updated_at_utc DESC,t.id DESC "
                "LIMIT %s OFFSET %s",
                (*parameters, query.page_size, offset),
            )
            items = [_ticket_view(_ticket(row)) for row in cursor.fetchall() or ()]
        return {"items": items, "total": total, "page": query.page, "page_size": query.page_size}

    def update(self, ticket_id, current_version, status, note, admin_user_id) -> CustomerServiceTicket:
        resolved = "UTC_TIMESTAMP()" if status is CustomerServiceStatus.RESOLVED else "NULL"
        sql = _UPDATE_TICKET_SQL.format(resolved_at=resolved)
        with self._connection.cursor() as cursor:
            cursor.execute(sql, (status.value, note, admin_user_id, ticket_id, current_version))
            if cursor.rowcount != 1:
                raise CustomerServiceVersionConflictError("客服需求已更新，請重新載入")
        return self.get(ticket_id)

    def append_agent_reply(self, ticket_id, event_key, reply_text, actor_id) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_EVENT_INSERT_SQL, (ticket_id, event_key, "agent_reply", reply_text, actor_id))

    def append_management_event(self, ticket_id, event_key, event_type, text, actor_id) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_EVENT_INSERT_SQL, (ticket_id, event_key, event_type, text, actor_id))

    def latest_client_case(self, line_user_id: str) -> dict[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_LATEST_CLIENT_CASE_SQL, (line_user_id,))
            return cursor.fetchone()

    def staff_subject(self, line_user_id: str) -> dict[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_STAFF_SUBJECT_SQL, (line_user_id,))
            return cursor.fetchone()

    def staff_orders(self, staff_id: int, keyword: str) -> list[dict[str, Any]]:
        pattern = f"%{keyword}%"
        with self._connection.cursor() as cursor:
            cursor.execute(_STAFF_ORDER_SQL, (staff_id, pattern, pattern))
            return list(cursor.fetchall() or ())

    def _ticket_for_event(self, event_key: str) -> CustomerServiceTicket | None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT ticket_id FROM customer_service_ticket_events WHERE event_key=%s", (event_key,))
            row = cursor.fetchone()
        return self.get(int(row["ticket_id"])) if row else None

    def _active_ticket(self, line_user_id, category) -> CustomerServiceTicket | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ACTIVE_TICKET_SQL, (line_user_id, category.value))
            row = cursor.fetchone()
        return _ticket(row) if row else None

    def _latest_ticket(self, line_user_id, category) -> CustomerServiceTicket | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_LATEST_TICKET_SQL, (line_user_id, category.value))
            row = cursor.fetchone()
        return _ticket(row) if row else None

    def _create_ticket(self, command) -> CustomerServiceTicket:
        context = self.latest_client_case(command.line_user_id) or {}
        with self._connection.cursor() as cursor:
            cursor.execute(_TICKET_INSERT_SQL, (command.line_user_id, context.get("client_id"), context.get("case_no"), command.category.value))
            ticket_id = int(cursor.lastrowid)
        return self.get(ticket_id)

    def _append_event(self, ticket_id, command) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_EVENT_INSERT_SQL, (ticket_id, command.event_key, "customer_message", command.message, f"line:{command.line_user_id}"))
            cursor.execute("UPDATE customer_service_tickets SET status=IF(status='resolved','handling',status),resolved_at_utc=NULL,version=version+1 WHERE id=%s", (ticket_id,))


def _ticket(row: dict[str, Any]) -> CustomerServiceTicket:
    return CustomerServiceTicket(
        ticket_id=int(row["id"]),
        line_user_id=row["line_user_id"],
        category=CustomerServiceCategory(row["category"]),
        status=CustomerServiceStatus(row["status"]),
        version=int(row["version"]),
        client_id=row.get("client_id"),
        case_no=row.get("case_no"),
        client_name=row.get("client_name"),
        client_phone=row.get("client_phone"),
        assigned_admin_user_id=row.get("assigned_to_admin_user_id"),
        internal_note=row.get("internal_note"),
        created_at=row.get("created_at_utc"),
        updated_at=row.get("updated_at_utc"),
    )


def _ticket_view(ticket: CustomerServiceTicket) -> dict[str, Any]:
    return {
        "ticket_id": ticket.ticket_id, "line_user_id_masked": _mask(ticket.line_user_id),
        "category": ticket.category.value, "status": ticket.status.value, "version": ticket.version,
        "client_id": ticket.client_id, "case_no": ticket.case_no,
        "client_name": ticket.client_name, "client_phone": ticket.client_phone,
        "assigned_admin_user_id": ticket.assigned_admin_user_id, "internal_note": ticket.internal_note,
        "created_at": ticket.created_at, "updated_at": ticket.updated_at,
    }


def _mask(value: str) -> str:
    return value[:4] + "…" + value[-4:] if len(value) > 8 else value[:2] + "***"


def _admin_user_id(actor_id: str) -> int | None:
    if not isinstance(actor_id, str) or not actor_id.startswith("admin:"):
        return None
    raw = actor_id.removeprefix("admin:")
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def _list_filters(
    query: CustomerServiceListQuery,
) -> tuple[list[str], tuple[Any, ...]]:
    clauses: list[str] = ["1=1"]
    parameters: list[Any] = []
    if query.status is not None:
        clauses.append("t.status=%s")
        parameters.append(query.status.value)
    if query.category is not None:
        clauses.append("t.category=%s")
        parameters.append(query.category.value)
    if query.search:
        clauses.append("(t.case_no LIKE %s OR CAST(t.id AS CHAR) LIKE %s)")
        pattern = f"%{query.search.strip()}%"
        parameters.extend((pattern, pattern))
    return clauses, tuple(parameters)


_TICKET_SELECT = "SELECT t.*,c.name AS client_name,c.phone AS client_phone FROM customer_service_tickets t LEFT JOIN clients c ON c.id=t.client_id"
_ACTIVE_TICKET_SQL = _TICKET_SELECT + " WHERE t.line_user_id=%s AND t.category=%s AND t.status IN ('waiting','handling') FOR UPDATE"
_LATEST_TICKET_SQL = _TICKET_SELECT + " WHERE t.line_user_id=%s AND t.category=%s ORDER BY t.id DESC LIMIT 1 FOR UPDATE"
_TICKET_INSERT_SQL = "INSERT INTO customer_service_tickets (line_user_id,client_id,case_no,category) VALUES (%s,%s,%s,%s)"
_EVENT_INSERT_SQL = "INSERT INTO customer_service_ticket_events (ticket_id,event_key,event_type,message_text,actor_id) VALUES (%s,%s,%s,%s,%s)"
_EVENT_LIST_SQL = "SELECT id,event_type,message_text,actor_id,created_at_utc AS created_at FROM customer_service_ticket_events WHERE ticket_id=%s ORDER BY id"
_UPDATE_TICKET_SQL = "UPDATE customer_service_tickets SET status=%s,internal_note=%s,assigned_to_admin_user_id=COALESCE(%s,assigned_to_admin_user_id),resolved_at_utc={resolved_at},version=version+1 WHERE id=%s AND version=%s"
_SUMMARY_SQL = "SELECT SUM(status='waiting') waiting,SUM(status='handling') handling,SUM(status='resolved' AND DATE(resolved_at_utc)=UTC_DATE()) resolved_today FROM customer_service_tickets"
_LATEST_CLIENT_CASE_SQL = (
    "SELECT c.id client_id,c.name client_name,o.case_no,o.status,o.start_date,o.end_date "
    "FROM line_identity_bindings b "
    "JOIN clients c ON c.id=CAST(b.subject_reference AS UNSIGNED) "
    "LEFT JOIN orders o ON o.client_id=c.id "
    "WHERE b.line_user_id=%s AND b.subject_type='customer' "
    "AND b.binding_status='bound' "
    "ORDER BY o.created_at DESC,o.case_no DESC LIMIT 1"
)
_STAFF_SUBJECT_SQL = (
    "SELECT CAST(b.subject_reference AS UNSIGNED) AS staff_id,s.name AS staff_name "
    "FROM line_identity_bindings b "
    "JOIN staff s ON s.id=CAST(b.subject_reference AS UNSIGNED) "
    "WHERE b.line_user_id=%s AND b.subject_type='staff' AND b.binding_status='bound' "
    "LIMIT 1"
)
_STAFF_ORDER_SQL = "SELECT o.case_no,c.name client_name,c.phone client_phone,c.city,c.address,o.status order_status,o.start_date,o.end_date,o.service_days,o.service_hours_per_day,c.due_month,c.service_start_date,c.service_time,c.residence_type,c.delivery_type,c.service_type,c.baby_info,c.notes FROM case_staff_assignments a JOIN orders o ON o.case_no=a.case_no JOIN clients c ON c.id=o.client_id WHERE a.staff_id=%s AND (a.status IS NULL OR a.status<>'cancelled') AND (o.case_no LIKE %s OR c.name LIKE %s) ORDER BY o.start_date DESC,o.case_no DESC LIMIT 20"


__all__ = ["CustomerServiceTicketNotFoundError", "CustomerServiceVersionConflictError", "MySqlCustomerServiceRepository"]
