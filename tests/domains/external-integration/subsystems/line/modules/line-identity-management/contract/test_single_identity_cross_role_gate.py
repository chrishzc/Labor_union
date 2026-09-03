"""Single-active-role regression for LINE identity switching."""

from __future__ import annotations

import pytest

from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingStatus,
    LineIdentityClaim,
)
from infrastructure.mysql.line_identity_review_repository import MySqlLineIdentityRepository
from shared_kernel.identities import ExpectedVersion


class _Connection:
    def __init__(self, *, counts=None, role_row=None, list_rows=()):
        self.counts = counts or {"admin_count": 0, "customer_count": 0, "staff_count": 0}
        self.role_row = role_row
        self.list_rows = tuple(list_rows)
        self.calls = []

    def cursor(self):
        return _Cursor(self)


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 1
        self.lastrowid = 0
        self._one = None
        self._many = ()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters=()):
        sql = " ".join(statement.split())
        self.connection.calls.append((sql, tuple(parameters)))
        self.rowcount = 1
        self._one = None
        self._many = ()
        if sql.startswith("SELECT line_user_id FROM line_platform_users"):
            self._one = {"line_user_id": parameters[0]}
        elif "AS admin_count" in sql and "AS customer_count" in sql and "AS staff_count" in sql:
            self._one = dict(self.connection.counts)
        elif "FROM line_identity_role_bindings WHERE line_user_id=%s AND subject_type=%s FOR UPDATE" in sql:
            self._one = self.connection.role_row
        elif "FROM line_identity_role_bindings WHERE line_user_id=%s ORDER BY subject_type" in sql:
            self._many = self.connection.list_rows

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


def _row(line_user_id: str, subject_type: str, reference: str):
    return {
        "line_user_id": line_user_id,
        "binding_status": "bound",
        "subject_type": subject_type,
        "subject_reference": reference,
        "aggregate_version": 1,
    }


def test_customer_must_be_revoked_before_staff_claim() -> None:
    connection = _Connection(
        counts={"admin_count": 0, "customer_count": 1, "staff_count": 0}
    )
    repository = MySqlLineIdentityRepository(connection)

    with pytest.raises(RuntimeError, match="line_identity_role_change_requires_revocation"):
        repository.save_claim(
            LineIdentityClaim(
                LineUserId("U-switch"),
                LineBindingSubjectType.STAFF,
                "18",
            ),
            ExpectedVersion(0),
        )

    assert not any(
        sql.startswith("INSERT INTO line_identity_role_bindings")
        for sql, _ in connection.calls
    )


def test_staff_claim_is_allowed_after_customer_revocation_completed() -> None:
    connection = _Connection(
        counts={"admin_count": 0, "customer_count": 0, "staff_count": 0}
    )
    repository = MySqlLineIdentityRepository(connection)

    result = repository.save_claim(
        LineIdentityClaim(
            LineUserId("U-switch"),
            LineBindingSubjectType.STAFF,
            "18",
        ),
        ExpectedVersion(0),
    )

    assert result.status is LineIdentityBindingStatus.PENDING_REVIEW
    assert result.subject_type is LineBindingSubjectType.STAFF
    assert result.version == ExpectedVersion(1)


def test_unscoped_read_fails_closed_if_old_data_contains_multiple_active_roles() -> None:
    connection = _Connection(
        list_rows=(
            _row("U-corrupt", "customer", "23"),
            _row("U-corrupt", "staff", "18"),
        )
    )
    repository = MySqlLineIdentityRepository(connection)

    with pytest.raises(RuntimeError, match="line_identity_multiple_active_binding"):
        repository.get(LineUserId("U-corrupt"))
