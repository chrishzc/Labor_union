"""Regression contracts for role-scoped LINE revocation/rebind gating."""

from __future__ import annotations

import pytest

from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingConflict,
    LineIdentityBindingStatus,
    LineIdentityClaim,
)
from infrastructure.mysql.line_identity_review_repository import (
    MySqlLineIdentityRepository,
    _IDENTITY_ROLE_SCOPE_COUNTS_SQL,
)
from shared_kernel.identities import ExpectedVersion


_LINE_USER_ID = LineUserId("U-rebind-gate")


def _binding(subject_type, reference, *, status, version):
    return {
        "line_user_id": _LINE_USER_ID.value,
        "binding_status": status,
        "subject_type": subject_type,
        "subject_reference": reference,
        "aggregate_version": version,
    }


class _Cursor:
    def __init__(self, *, one_rows=()) -> None:
        self.one_rows = list(one_rows)
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


class _Connection:
    def __init__(self, cursor) -> None:
        self.cursor_instance = cursor

    def cursor(self):
        return self.cursor_instance


def _claim(subject_type, reference):
    return LineIdentityClaim(_LINE_USER_ID, subject_type, reference)


def test_same_role_new_claim_waits_for_revocation_completion() -> None:
    cursor = _Cursor(
        one_rows=(
            {"line_user_id": _LINE_USER_ID.value},
            {"admin_count": 0, "nonadmin_count": 1},
            _binding(
                "customer",
                "customer:7",
                status="revocation_pending",
                version=2,
            ),
        )
    )
    repository = MySqlLineIdentityRepository(_Connection(cursor))

    with pytest.raises(
        LineIdentityBindingConflict,
        match="cannot transition LINE binding from revocation_pending to pending_review",
    ):
        repository.save_claim(
            _claim(LineBindingSubjectType.CUSTOMER, "customer:9"),
            ExpectedVersion(2),
        )

    assert not any(
        statement.startswith("UPDATE line_identity_role_bindings")
        for statement, _parameters in cursor.executed
    )


def test_same_role_new_claim_is_allowed_after_revocation_completed() -> None:
    cursor = _Cursor(
        one_rows=(
            {"line_user_id": _LINE_USER_ID.value},
            {"admin_count": 0, "nonadmin_count": 0},
            _binding("customer", "customer:7", status="revoked", version=3),
        )
    )
    repository = MySqlLineIdentityRepository(_Connection(cursor))

    result = repository.save_claim(
        _claim(LineBindingSubjectType.CUSTOMER, "customer:9"),
        ExpectedVersion(3),
    )

    assert result.status is LineIdentityBindingStatus.PENDING_REVIEW
    assert result.subject_type is LineBindingSubjectType.CUSTOMER
    assert result.subject_reference == "customer:9"
    assert result.version == ExpectedVersion(4)


def test_admin_revocation_pending_remains_exclusive_until_completion() -> None:
    assert "'revocation_pending'" in _IDENTITY_ROLE_SCOPE_COUNTS_SQL

    pending_cursor = _Cursor(
        one_rows=(
            {"line_user_id": _LINE_USER_ID.value},
            {"admin_count": 1, "nonadmin_count": 0},
        )
    )
    pending_repository = MySqlLineIdentityRepository(_Connection(pending_cursor))

    with pytest.raises(RuntimeError, match="line_identity_admin_role_exclusive"):
        pending_repository.save_claim(
            _claim(LineBindingSubjectType.CUSTOMER, "customer:9"),
            ExpectedVersion(0),
        )

    completed_cursor = _Cursor(
        one_rows=(
            {"line_user_id": _LINE_USER_ID.value},
            {"admin_count": 0, "nonadmin_count": 0},
            None,
        )
    )
    completed_repository = MySqlLineIdentityRepository(_Connection(completed_cursor))

    result = completed_repository.save_claim(
        _claim(LineBindingSubjectType.CUSTOMER, "customer:9"),
        ExpectedVersion(0),
    )

    assert result.status is LineIdentityBindingStatus.PENDING_REVIEW
    assert result.subject_type is LineBindingSubjectType.CUSTOMER
