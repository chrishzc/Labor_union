"""MySQL read model and saga roots for LINE identity management."""

from __future__ import annotations

from typing import Any

from domains.line.identities import LineUserId
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from shared_kernel.identities import ExpectedVersion
from subsystems.line.identity_management_contracts import (
    LineIdentityBindingListQuery,
    LineIdentityBindingManagementView,
    LineIdentityBindingPage,
    LineIdentityRevocationRequest,
    LineIdentityRevocationStatus,
)


class MySqlLineIdentityManagementRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list(self, query: LineIdentityBindingListQuery) -> LineIdentityBindingPage:
        clauses, parameters = _filters(query)
        where = " AND ".join(clauses)
        offset = (query.page - 1) * query.page_size
        with self._connection.cursor() as cursor:
            cursor.execute(_COUNT_SQL.format(where=where), parameters)
            total = int((cursor.fetchone() or {}).get("total") or 0)
            cursor.execute(
                _LIST_SQL.format(where=where),
                (*parameters, query.page_size, offset),
            )
            items = tuple(_binding_view(row) for row in cursor.fetchall() or ())
        return LineIdentityBindingPage(items, total, query.page, query.page_size)

    def detail(self, line_user_id: LineUserId) -> LineIdentityBindingManagementView:
        with self._connection.cursor() as cursor:
            cursor.execute(_DETAIL_SQL, (line_user_id.value,))
            row = cursor.fetchone()
        if not row:
            raise LookupError("line_identity_binding_not_found")
        return _binding_view(row)

    def default_menu_publication(self) -> dict[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_DEFAULT_MENU_SQL)
            return cursor.fetchone()

    def subject_candidate(
        self,
        subject_type: LineBindingSubjectType,
        subject_reference: str,
    ) -> dict[str, Any] | None:
        table, id_column, line_column, name_column = _SUBJECT_COLUMNS[subject_type]
        statement = (
            f"SELECT {id_column} AS subject_reference,{name_column} AS subject_name,"
            f"{line_column} AS line_user_id FROM {table} WHERE {id_column}=%s"
        )
        with self._connection.cursor() as cursor:
            cursor.execute(statement, (int(subject_reference),))
            return cursor.fetchone()

    def get_request(
        self,
        request_id: int,
        *,
        lock: bool = False,
    ) -> LineIdentityRevocationRequest:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_REQUEST_SELECT_SQL + suffix, (request_id,))
            row = cursor.fetchone()
        if not row:
            raise LookupError("line_identity_revocation_not_found")
        return _revocation_request(row)

    def get_request_by_key(self, key: str) -> LineIdentityRevocationRequest | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_REQUEST_BY_KEY_SQL, (key,))
            row = cursor.fetchone()
        return _revocation_request(row) if row else None

    # Kept cohesive so every immutable saga root field maps through one INSERT/readback.
    def create_request(
        self,
        command,
        pending_binding,
        publication: dict[str, Any],
    ) -> LineIdentityRevocationRequest:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _REQUEST_INSERT_SQL,
                (
                    command.line_user_id.value,
                    pending_binding.subject_type.value,
                    pending_binding.subject_reference,
                    command.expected_version.value,
                    pending_binding.version.value,
                    int(publication["id"]),
                    str(publication["line_rich_menu_id"]),
                    command.actor.actor_id,
                    command.reason,
                    command.idempotency_key.value,
                    command.correlation_id.value,
                ),
            )
            request_id = int(cursor.lastrowid)
        return self.get_request(request_id)

    def mark_failure(
        self,
        request_id: int,
        code: str,
        message: str,
        *,
        terminal: bool,
    ) -> None:
        status = "menu_reset_failed" if terminal else "pending_menu_reset"
        with self._connection.cursor() as cursor:
            cursor.execute(_REQUEST_FAILURE_SQL, (status, code, message, request_id))
            if cursor.rowcount != 1:
                raise RuntimeError("line_identity_revocation_state_conflict")

    # Kept cohesive so optimistic request completion and audit fields cannot diverge.
    def complete(
        self,
        request: LineIdentityRevocationRequest,
        completed_version: ExpectedVersion,
        actor_id: str,
        *,
        manual: bool = False,
        reason: str | None = None,
    ) -> None:
        status = "manual_completed" if manual else "completed"
        with self._connection.cursor() as cursor:
            cursor.execute(
                _REQUEST_COMPLETE_SQL,
                (
                    status,
                    completed_version.value,
                    status,
                    actor_id,
                    reason,
                    request.request_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_identity_revocation_state_conflict")

def _filters(query: LineIdentityBindingListQuery) -> tuple[list[str], tuple[Any, ...]]:
    clauses = ["b.subject_type IS NOT NULL", "b.subject_reference IS NOT NULL"]
    parameters: list[Any] = []
    if query.status is not None:
        clauses.append("b.binding_status=%s")
        parameters.append(query.status.value)
    if query.subject_type is not None:
        clauses.append("b.subject_type=%s")
        parameters.append(query.subject_type.value)
    if query.search.strip():
        pattern = f"%{query.search.strip()}%"
        clauses.append("(b.line_user_id LIKE %s OR " + _SUBJECT_NAME_SQL + " LIKE %s)")
        parameters.extend((pattern, pattern))
    return clauses, tuple(parameters)


# Kept cohesive because this is one database-row-to-typed-view mapping boundary.
def _binding_view(row: dict[str, Any]) -> LineIdentityBindingManagementView:
    revocation_status = row.get("request_status")
    return LineIdentityBindingManagementView(
        line_user_id=str(row["line_user_id"]),
        status=LineIdentityBindingStatus(str(row["binding_status"])),
        version=int(row["aggregate_version"]),
        subject_type=LineBindingSubjectType(str(row["subject_type"])),
        subject_reference=str(row["subject_reference"]),
        subject_name=str(row.get("subject_name") or "-"),
        updated_at=row.get("updated_at_utc"),
        revocation_request_id=(
            int(row["revocation_request_id"])
            if row.get("revocation_request_id") is not None
            else None
        ),
        revocation_status=(
            LineIdentityRevocationStatus(str(revocation_status))
            if revocation_status
            else None
        ),
        revoked_at=row.get("revoked_at_utc"),
    )


def _revocation_request(row: dict[str, Any]) -> LineIdentityRevocationRequest:
    return LineIdentityRevocationRequest(
        request_id=int(row["id"]),
        line_user_id=LineUserId(str(row["line_user_id"])),
        subject_type=LineBindingSubjectType(str(row["subject_type"])),
        subject_reference=str(row["subject_reference"]),
        status=LineIdentityRevocationStatus(str(row["request_status"])),
        requested_binding_version=ExpectedVersion(int(row["requested_binding_version"])),
        pending_binding_version=ExpectedVersion(int(row["pending_binding_version"])),
        publication_id=int(row["default_menu_publication_id"]),
        provider_menu_id=str(row["provider_menu_id"]),
        requested_by_actor_id=str(row["requested_by_actor_id"]),
        reason=str(row["request_reason"]),
        idempotency_key=str(row["idempotency_key"]),
        correlation_id=str(row["correlation_id"]),
        attempt_count=int(row["attempt_count"]),
        last_error_code=row.get("last_error_code"),
        last_error_message=row.get("last_error_message"),
    )


_SUBJECT_NAME_SQL = (
    "COALESCE(c.name,s.name,a.display_name,'-')"
)
_BASE_SELECT = (
    "SELECT b.line_user_id,b.binding_status,b.aggregate_version,b.subject_type,"
    "b.subject_reference,b.updated_at_utc,"
    + _SUBJECT_NAME_SQL
    + " AS subject_name,r.id AS revocation_request_id,r.request_status,"
    "(SELECT MAX(e.occurred_at_utc) FROM line_identity_binding_events e "
    "WHERE e.line_user_id=b.line_user_id AND e.action='revoked') AS revoked_at_utc "
    "FROM line_identity_bindings b "
    "LEFT JOIN clients c ON b.subject_type='customer' AND c.id=CAST(b.subject_reference AS UNSIGNED) "
    "LEFT JOIN staff s ON b.subject_type='staff' AND s.id=CAST(b.subject_reference AS UNSIGNED) "
    "LEFT JOIN admin_users a ON b.subject_type='admin' AND a.id=CAST(b.subject_reference AS UNSIGNED) "
    "LEFT JOIN line_identity_revocation_requests r ON r.line_user_id=b.line_user_id "
    "AND r.active_marker=1 "
)
_LIST_SQL = _BASE_SELECT + "WHERE {where} ORDER BY b.updated_at_utc DESC LIMIT %s OFFSET %s"
_DETAIL_SQL = _BASE_SELECT + "WHERE b.line_user_id=%s"
_COUNT_SQL = "SELECT COUNT(*) total FROM (" + _BASE_SELECT + "WHERE {where}) counted"
_DEFAULT_MENU_SQL = (
    "SELECT id,provider_menu_id AS line_rich_menu_id "
    "FROM line_rich_menu_publication_tasks "
    "WHERE menu_definition_id='default_menu' AND publication_status='published' "
    "AND provider_menu_id IS NOT NULL ORDER BY id DESC LIMIT 1"
)
_REQUEST_SELECT_SQL = (
    "SELECT id,line_user_id,subject_type,subject_reference,request_status,"
    "requested_binding_version,pending_binding_version,"
    "COALESCE(canonical_default_menu_publication_id,default_menu_publication_id) "
    "AS default_menu_publication_id,"
    "provider_menu_id,requested_by_actor_id,request_reason,idempotency_key,"
    "correlation_id,attempt_count,last_error_code,"
    "last_error_message FROM line_identity_revocation_requests WHERE id=%s"
)
_REQUEST_BY_KEY_SQL = _REQUEST_SELECT_SQL.replace("WHERE id=%s", "WHERE idempotency_key=%s")
_REQUEST_INSERT_SQL = (
    "INSERT INTO line_identity_revocation_requests (line_user_id,subject_type,"
    "subject_reference,requested_binding_version,pending_binding_version,"
    "canonical_default_menu_publication_id,provider_menu_id,requested_by_actor_id,"
    "request_reason,idempotency_key,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_REQUEST_FAILURE_SQL = (
    "UPDATE line_identity_revocation_requests SET request_status=%s,"
    "attempt_count=attempt_count+1,last_error_code=%s,last_error_message=%s "
    "WHERE id=%s AND request_status IN ('pending_menu_reset','menu_reset_failed')"
)
_REQUEST_COMPLETE_SQL = (
    "UPDATE line_identity_revocation_requests SET request_status=%s,"
    "completed_binding_version=%s,attempt_count=attempt_count+1,"
    "menu_reset_at_utc=IF(%s='completed',CURRENT_TIMESTAMP(6),menu_reset_at_utc),"
    "completed_at_utc=CURRENT_TIMESTAMP(6),completed_by_actor_id=%s,"
    "completion_reason=%s,last_error_code=NULL,last_error_message=NULL "
    "WHERE id=%s AND request_status IN ('pending_menu_reset','menu_reset_failed')"
)
_SUBJECT_COLUMNS = {
    LineBindingSubjectType.CUSTOMER: ("clients", "id", "line_user_id", "name"),
    LineBindingSubjectType.STAFF: ("staff", "id", "line_user_id", "name"),
    LineBindingSubjectType.ADMIN: (
        "admin_users",
        "id",
        "linked_line_user_id",
        "display_name",
    ),
}


__all__ = ["MySqlLineIdentityManagementRepository"]
