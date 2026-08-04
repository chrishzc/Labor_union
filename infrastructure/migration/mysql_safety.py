"""MySQL adapters for migration principal safety evidence."""

from __future__ import annotations

from typing import Any

from infrastructure.migration.maintenance import (
    SourcePrincipalEvidence,
    validate_source_read_only_principal,
)


def inspect_source_read_only_principal(
    config: Any,
    source_database: str,
) -> SourcePrincipalEvidence:
    connection = config.connect(source_database)
    try:
        with connection.cursor() as cursor:
            principal = _read_current_principal(cursor)
            _require_source_database(cursor, source_database)
            _require_no_active_roles(cursor)
            privileges = _read_effective_privileges(
                cursor, principal, source_database
            )
    finally:
        connection.close()
    evidence = SourcePrincipalEvidence(
        principal=principal,
        source_database=source_database,
        privileges=frozenset(privileges),
    )
    return validate_source_read_only_principal(evidence)


def _read_current_principal(cursor: Any) -> str:
    cursor.execute("SELECT CURRENT_USER() AS principal")
    row = cursor.fetchone() or {}
    principal = str(
        row.get("principal") or row.get("PRINCIPAL") or ""
    ).strip()
    if not principal:
        raise ValueError("source principal identity is unavailable")
    return principal


def _require_source_database(cursor: Any, expected_database: str) -> None:
    cursor.execute("SELECT DATABASE() AS source_database")
    row = cursor.fetchone() or {}
    actual_database = str(
        row.get("source_database") or row.get("SOURCE_DATABASE") or ""
    )
    if actual_database != expected_database:
        raise ValueError("source principal database identity mismatch")


def _require_no_active_roles(cursor: Any) -> None:
    cursor.execute("SELECT CURRENT_ROLE() AS active_roles")
    row = cursor.fetchone() or {}
    active_roles = str(
        row.get("active_roles") or row.get("ACTIVE_ROLES") or "NONE"
    ).strip()
    if active_roles.upper() != "NONE":
        raise ValueError("source principal active roles are not supported")


def _read_effective_privileges(
    cursor: Any,
    principal: str,
    source_database: str,
) -> set[str]:
    grantee = _information_schema_grantee(principal)
    cursor.execute(
        "SELECT privilege_type FROM information_schema.user_privileges "
        "WHERE grantee=%s "
        "UNION SELECT privilege_type FROM information_schema.schema_privileges "
        "WHERE grantee=%s AND table_schema=%s "
        "UNION SELECT privilege_type FROM information_schema.table_privileges "
        "WHERE grantee=%s AND table_schema=%s",
        (grantee, grantee, source_database, grantee, source_database),
    )
    return {
        str(row.get("privilege_type") or row.get("PRIVILEGE_TYPE") or "").upper()
        for row in cursor.fetchall()
    }


def _information_schema_grantee(principal: str) -> str:
    if "@" not in principal:
        raise ValueError("source principal identity is malformed")
    user, host = principal.rsplit("@", 1)
    escaped_user = user.replace("'", "''")
    escaped_host = host.replace("'", "''")
    return f"'{escaped_user}'@'{escaped_host}'"
