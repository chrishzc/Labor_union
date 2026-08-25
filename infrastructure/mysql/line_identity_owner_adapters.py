"""File: line_identity_owner_adapters.py
Description: 提供 LINE 身分 owner projection 的唯讀與綁定資料庫 adapter。
"""

from __future__ import annotations

from typing import Any

from domains.line.identities import LineUserId
from domains.line.identity_binding import LineBindingSubjectType
from subsystems.access.authentication_session import verify_admin_password
from subsystems.line.identity_contracts import (
    AdminCredentialProof,
    CustomerIdentityProof,
    LineIdentityCandidate,
    StaffIdentityProof,
)
from subsystems.line.order_group_contracts import LinkedLineAdmin


class MySqlCustomerIdentityOwnerAdapter:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def resolve_customer(self, proof: CustomerIdentityProof) -> LineIdentityCandidate | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CUSTOMER_RESOLVE_SQL,
                (proof.name.strip(), _normalized_phone(proof.phone)),
            )
            rows = tuple(cursor.fetchall() or ())
        if not rows:
            return None
        if len(rows) != 1:
            raise RuntimeError("customer_identity_ambiguous")
        row = rows[0]
        return _candidate(LineBindingSubjectType.CUSTOMER, row)

    def bind_customer(self, subject_reference, line_user_id, expected_current_line_user_id):
        customer_id = _numeric_subject_reference(subject_reference, "customer")
        with self._connection.cursor() as cursor:
            cursor.execute(_CUSTOMER_LOCK_SQL, (customer_id,))
            row = cursor.fetchone()
            if not row:
                raise LookupError("customer_identity_not_found")
            current = _optional_line_user_id(row.get("line_user_id"))
            if current != expected_current_line_user_id:
                raise RuntimeError("customer_identity_binding_conflict")
            cursor.execute(_CUSTOMER_LINE_COLLISION_SQL, (line_user_id.value, customer_id))
            if cursor.fetchone():
                raise RuntimeError("line_identity_already_used_by_customer")
            cursor.execute(_CUSTOMER_BIND_SQL, (line_user_id.value, customer_id))
            _upsert_legacy_role(cursor, line_user_id, "customer")

    def clear_customer(self, subject_reference, line_user_id) -> None:
        _clear_owner_line_user(
            self._connection,
            "clients",
            "line_user_id",
            subject_reference,
            line_user_id,
        )


class MySqlStaffIdentityOwnerAdapter:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def resolve_staff(self, proof: StaffIdentityProof) -> LineIdentityCandidate | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _STAFF_RESOLVE_SQL,
                (proof.name.strip(), proof.identity_card.strip().upper(), proof.birthday),
            )
            rows = tuple(cursor.fetchall() or ())
        if not rows:
            return None
        if len(rows) != 1:
            raise RuntimeError("staff_identity_ambiguous")
        return _candidate(LineBindingSubjectType.STAFF, rows[0])

    def bind_staff(
        self,
        subject_reference: str,
        line_user_id: LineUserId,
        expected_current_line_user_id: LineUserId | None,
    ) -> None:
        staff_id = _numeric_subject_reference(subject_reference, "staff")
        with self._connection.cursor() as cursor:
            cursor.execute(_STAFF_LOCK_SQL, (staff_id,))
            row = cursor.fetchone()
            if not row:
                raise LookupError("staff_identity_not_found")
            cursor.execute(_STAFF_LINE_COLLISION_SQL, (line_user_id.value, staff_id))
            if cursor.fetchone():
                raise RuntimeError("line_identity_already_used_by_staff")
            current = _optional_line_user_id(row.get("line_user_id"))
            if current != expected_current_line_user_id:
                raise RuntimeError("staff_identity_binding_conflict")
            cursor.execute(_STAFF_BIND_SQL, (line_user_id.value, staff_id))
            _upsert_legacy_role(cursor, line_user_id, "staff")

    def clear_staff(self, subject_reference, line_user_id) -> None:
        _clear_owner_line_user(
            self._connection,
            "staff",
            "line_user_id",
            subject_reference,
            line_user_id,
        )


class MySqlAdminIdentityOwnerAdapter:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def authenticate_admin(
        self,
        proof: AdminCredentialProof,
    ) -> LineIdentityCandidate | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ADMIN_AUTH_SQL, (proof.username.strip().lower(),))
            row = cursor.fetchone()
        if not row or not row["enabled"]:
            return None
        if not verify_admin_password(proof.password, str(row["password_hash"])):
            return None
        return _candidate(LineBindingSubjectType.ADMIN, row)

    def bind_admin(
        self,
        subject_reference: str,
        line_user_id: LineUserId,
        expected_current_line_user_id: LineUserId | None,
    ) -> None:
        admin_id = _numeric_subject_reference(subject_reference, "admin")
        with self._connection.cursor() as cursor:
            cursor.execute(_ADMIN_LOCK_SQL, (admin_id,))
            row = cursor.fetchone()
            if not row or not row["enabled"]:
                raise LookupError("admin_identity_not_found")
            cursor.execute(_ADMIN_LINE_COLLISION_SQL, (line_user_id.value, admin_id))
            if cursor.fetchone():
                raise RuntimeError("line_identity_already_used_by_admin")
            current = _optional_line_user_id(row.get("linked_line_user_id"))
            if current != expected_current_line_user_id:
                raise RuntimeError("admin_identity_binding_conflict")
            _upsert_legacy_role(cursor, line_user_id, "union_staff")
            cursor.execute(_ADMIN_BIND_SQL, (line_user_id.value, admin_id))

    def clear_admin(self, subject_reference, line_user_id) -> None:
        _clear_owner_line_user(
            self._connection,
            "admin_users",
            "linked_line_user_id",
            subject_reference,
            line_user_id,
        )

    def get_linked_admin(self, line_user_id: LineUserId) -> LinkedLineAdmin | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ADMIN_LINKED_SQL, (line_user_id.value,))
            row = cursor.fetchone()
        if not row:
            return None
        return LinkedLineAdmin(
            int(row["id"]),
            str(row["display_name"]),
            str(row["role"]),
            line_user_id,
        )


def _candidate(subject_type, row):
    raw_line_user_id = row.get("line_user_id")
    if subject_type is LineBindingSubjectType.ADMIN:
        raw_line_user_id = row.get("linked_line_user_id")
    return LineIdentityCandidate(
        subject_type,
        str(row["id"]),
        _optional_line_user_id(raw_line_user_id),
    )


def _normalized_phone(phone: str) -> str:
    return phone.replace(" ", "").replace("-", "")


def _optional_line_user_id(value: object) -> LineUserId | None:
    text = str(value or "").strip()
    return LineUserId(text) if text else None


def _numeric_subject_reference(value: str, owner: str) -> int:
    try:
        identity = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{owner} subject reference is invalid") from error
    if identity < 1:
        raise ValueError(f"{owner} subject reference is invalid")
    return identity


def _upsert_legacy_role(cursor, line_user_id, role):
    cursor.execute(_LEGACY_ROLE_UPSERT_SQL, (line_user_id.value, role))


def _clear_owner_line_user(
    connection,
    table: str,
    column: str,
    subject_reference: str,
    line_user_id: LineUserId,
) -> None:
    owner_id = _numeric_subject_reference(subject_reference, table)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET {column}=NULL WHERE id=%s AND {column}=%s",
            (owner_id, line_user_id.value),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("line_identity_owner_projection_conflict")
        # Legacy publication still reads this projection; downgrade prevents future relinking.
        _upsert_legacy_role(cursor, line_user_id, "customer")


_CUSTOMER_RESOLVE_SQL = (
    "SELECT id,line_user_id FROM clients WHERE name=%s AND "
    "REPLACE(REPLACE(phone,'-',''),' ','')=%s ORDER BY id LIMIT 2"
)
_CUSTOMER_LOCK_SQL = "SELECT id,line_user_id FROM clients WHERE id=%s FOR UPDATE"
_CUSTOMER_LINE_COLLISION_SQL = (
    "SELECT id FROM clients WHERE line_user_id=%s AND id<>%s LIMIT 1 FOR UPDATE"
)
_CUSTOMER_BIND_SQL = "UPDATE clients SET line_user_id=%s WHERE id=%s"
_STAFF_RESOLVE_SQL = (
    "SELECT id,line_user_id FROM staff WHERE name=%s AND UPPER(identity_card)=%s "
    "AND birthday=%s LIMIT 2"
)
_STAFF_LOCK_SQL = "SELECT id,line_user_id FROM staff WHERE id=%s FOR UPDATE"
_STAFF_LINE_COLLISION_SQL = (
    "SELECT id FROM staff WHERE line_user_id=%s AND id<>%s LIMIT 1 FOR UPDATE"
)
_STAFF_BIND_SQL = "UPDATE staff SET line_user_id=%s WHERE id=%s"
_ADMIN_AUTH_SQL = (
    "SELECT id,password_hash,enabled,linked_line_user_id FROM admin_users "
    "WHERE username=%s FOR UPDATE"
)
_ADMIN_LOCK_SQL = (
    "SELECT id,enabled,linked_line_user_id FROM admin_users WHERE id=%s FOR UPDATE"
)
_ADMIN_LINE_COLLISION_SQL = (
    "SELECT id FROM admin_users WHERE linked_line_user_id=%s AND id<>%s LIMIT 1 FOR UPDATE"
)
_ADMIN_BIND_SQL = "UPDATE admin_users SET linked_line_user_id=%s WHERE id=%s"
_ADMIN_LINKED_SQL = (
    "SELECT a.id,a.display_name,a.role FROM admin_users a "
    "JOIN line_identity_bindings b ON "
    "CONVERT(b.line_user_id USING utf8mb4) COLLATE utf8mb4_unicode_ci="
    "CONVERT(a.linked_line_user_id USING utf8mb4) COLLATE utf8mb4_unicode_ci "
    "AND b.subject_type='admin' AND "
    "CONVERT(b.subject_reference USING utf8mb4) COLLATE utf8mb4_unicode_ci="
    "CONVERT(CAST(a.id AS CHAR) USING utf8mb4) COLLATE utf8mb4_unicode_ci "
    "AND b.binding_status='bound' "
    "WHERE CONVERT(a.linked_line_user_id USING utf8mb4) COLLATE utf8mb4_unicode_ci="
    "CONVERT(%s USING utf8mb4) COLLATE utf8mb4_unicode_ci "
    "AND a.enabled=1 LIMIT 1"
)
_LEGACY_ROLE_UPSERT_SQL = (
    "INSERT INTO line_users (line_user_id,role,status,last_event_at) "
    "VALUES (%s,%s,'active',UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE "
    "role=VALUES(role),status='active',last_event_at=UTC_TIMESTAMP()"
)


__all__ = [
    "MySqlAdminIdentityOwnerAdapter",
    "MySqlCustomerIdentityOwnerAdapter",
    "MySqlStaffIdentityOwnerAdapter",
]
