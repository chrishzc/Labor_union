"""Repository-level negative contracts for role-scoped LINE identity."""

from __future__ import annotations

import os

import pytest

from domains.line.identities import LineUserId
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityClaim
from infrastructure.mysql.line_identity_review_repository import (
    MySqlLineIdentityRepository,
)
from infrastructure.mysql.line_identity_management_repository import (
    MySqlLineIdentityManagementRepository,
    _CURRENT_FACT_SQL,
)
from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection
from shared_kernel.identities import ExpectedVersion
from subsystems.line.identity_management_contracts import LineIdentityCurrentFactQuery


def _binding(subject_type, reference, *, status="bound", version=1):
    return {
        "line_user_id": "U-role-negative",
        "binding_status": status,
        "subject_type": subject_type,
        "subject_reference": reference,
        "aggregate_version": version,
    }


class _Cursor:
    def __init__(self, *, one_rows=(), all_rows=()) -> None:
        self.one_rows = list(one_rows)
        self.all_rows = list(all_rows)
        self.executed = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, parameters=()):
        parameters = tuple(parameters)
        assert statement.count("%s") == len(parameters)
        self.executed.append((statement, parameters))

    def fetchone(self):
        return self.one_rows.pop(0) if self.one_rows else None

    def fetchall(self):
        return self.all_rows.pop(0) if self.all_rows else ()


class _Connection:
    def __init__(self, cursor) -> None:
        self.cursor_instance = cursor

    def cursor(self):
        return self.cursor_instance


def test_multiple_active_roles_fail_closed_until_conflicting_role_is_revoked() -> None:
    rows = (
        _binding("customer", "customer:7"),
        _binding("staff", "staff:8"),
    )
    cursor = _Cursor(all_rows=(rows,))
    repository = MySqlLineIdentityRepository(_Connection(cursor))

    with pytest.raises(RuntimeError, match="line_identity_multiple_active_binding"):
        repository.get(LineUserId("U-role-negative"))
    assert len(cursor.executed) == 1


def test_management_detail_ignores_revoked_history_when_one_role_is_active() -> None:
    cursor = _Cursor(
        all_rows=((
            _binding("customer", "customer:7"),
            _binding("staff", "staff:8", status="revoked"),
        ),)
    )
    detail = MySqlLineIdentityManagementRepository(
        _Connection(cursor)
    ).detail(LineUserId("U-role-negative"))

    assert detail.subject_type is LineBindingSubjectType.CUSTOMER
    assert detail.subject_reference == "customer:7"
    assert len(cursor.executed) == 1


@pytest.mark.parametrize(
    ("subject_type", "counts"),
    (
        (
            LineBindingSubjectType.ADMIN,
            {"admin_count": 0, "customer_count": 1, "staff_count": 0},
        ),
        (
            LineBindingSubjectType.STAFF,
            {"admin_count": 1, "customer_count": 0, "staff_count": 0},
        ),
    ),
)
def test_role_change_requires_revoking_the_current_active_role(subject_type, counts) -> None:
    cursor = _Cursor(
        one_rows=(
            {"line_user_id": "U-role-negative"},
            counts,
        )
    )
    repository = MySqlLineIdentityRepository(_Connection(cursor))

    with pytest.raises(RuntimeError, match="line_identity_role_change_requires_revocation"):
        repository.save_claim(
            LineIdentityClaim(
                LineUserId("U-role-negative"),
                subject_type,
                f"{subject_type.value}:9",
            ),
            ExpectedVersion(0),
        )


def test_revoked_role_cannot_be_selected() -> None:
    cursor = _Cursor(one_rows=(_binding("staff", "staff:8", status="revoked"),))
    repository = MySqlLineIdentityRepository(_Connection(cursor))

    with pytest.raises(RuntimeError, match="line_identity_selected_role_not_bound"):
        repository.select_role(
            LineUserId("U-role-negative"),
            LineBindingSubjectType.STAFF,
            ExpectedVersion(4),
        )
    assert not any(
        statement.startswith("UPDATE line_platform_users")
        for statement, _parameters in cursor.executed
    )


def test_current_fact_union_casts_all_owner_ids_with_canonical_collation() -> None:
    """The four-arm readback must not inherit connection collation for IDs."""
    arms = _CURRENT_FACT_SQL.split("UNION ALL")

    assert len(arms) == 4
    for alias, arm in zip(("c", "s", "a"), arms[1:]):
        assert (
            f"CAST({alias}.id AS CHAR CHARACTER SET utf8mb4) "
            "COLLATE utf8mb4_unicode_ci"
        ) in arm


@pytest.mark.skipif(
    not os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE", "").startswith("lu_test_")
    or DB_CONFIG.get("database")
    != os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE", "").strip(),
    reason="requires an explicitly selected disposable lu_test_* MySQL database",
)
def test_current_fact_uses_default_connection_without_collation_session_workaround() -> None:
    database = os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"]
    line_user_id = "U-collation-regression-20260901"
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE(), @@collation_connection")
            selected_database, connection_collation = cursor.fetchone().values()
        assert selected_database == database
        assert connection_collation

        readback = MySqlLineIdentityManagementRepository(connection).current_fact(
            LineIdentityCurrentFactQuery(LineUserId(line_user_id))
        )

        assert readback.line_user_id == line_user_id
    finally:
        connection.close()
