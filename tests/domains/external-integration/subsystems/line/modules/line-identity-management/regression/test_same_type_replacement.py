"""Regression coverage for the LINE identity same-type replacement port."""

from __future__ import annotations

import pytest

from domains.line.identities import LineUserId
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityClaim
from infrastructure.mysql.line_identity_review_repository import MySqlLineIdentityRepository
from shared_kernel.identities import ExpectedVersion, IdempotencyKey


class ScriptedCursor:
    def __init__(self, *, one_rows=()) -> None:
        self.one_rows = list(one_rows)
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, parameters=()):
        normalized = tuple(parameters)
        assert sql.count("%s") == len(normalized)
        self.executed.append((sql, normalized))

    def fetchone(self):
        return self.one_rows.pop(0) if self.one_rows else None


class FakeConnection:
    def __init__(self, cursor: ScriptedCursor) -> None:
        self.cursor_instance = cursor

    def cursor(self):
        return self.cursor_instance


def test_bound_identity_replacement_updates_same_type_and_appends_one_rebound_event() -> None:
    cursor = ScriptedCursor(
        one_rows=(
            None,
            {"line_user_id": "U-staff"},
            {"admin_count": 0, "nonadmin_count": 1},
            {
                "line_user_id": "U-staff",
                "binding_status": "bound",
                "subject_type": "staff",
                "subject_reference": "staff:7",
                "aggregate_version": 3,
            },
        )
    )
    repository = MySqlLineIdentityRepository(FakeConnection(cursor))

    result = repository.replace_subject(
        LineIdentityClaim(
            LineUserId("U-staff"),
            LineBindingSubjectType.STAFF,
            "staff:8",
        ),
        ExpectedVersion(3),
        "admin:7",
        IdempotencyKey("identity-replace:u-staff:3"),
        "identity-replace:u-staff",
    )

    assert result.status.value == "bound"
    assert result.subject_type is LineBindingSubjectType.STAFF
    assert result.subject_reference == "staff:8"
    assert result.version == ExpectedVersion(4)
    update_sql, update_parameters = cursor.executed[4]
    assert update_sql.startswith("UPDATE line_identity_role_bindings")
    assert update_parameters == ("bound", "staff:8", 4, "U-staff", "staff", 3)
    event_statements = [
        (sql, parameters)
        for sql, parameters in cursor.executed
        if sql.startswith("INSERT INTO line_identity_role_binding_events")
    ]
    assert len(event_statements) == 1
    assert event_statements[0][1][:7] == (
        "U-staff",
        "rebound",
        "staff",
        "staff:8",
        3,
        4,
        "admin:7",
    )
    assert event_statements[0][1][8:] == (
        "identity-replace:u-staff:3",
        "identity-replace:u-staff",
    )


def test_bound_identity_replacement_rejects_unchanged_reference() -> None:
    cursor = ScriptedCursor(
        one_rows=(
            None,
            {"line_user_id": "U-staff"},
            {"admin_count": 0, "nonadmin_count": 1},
            {
                "line_user_id": "U-staff",
                "binding_status": "bound",
                "subject_type": "staff",
                "subject_reference": "staff:7",
                "aggregate_version": 3,
            },
        )
    )

    with pytest.raises(RuntimeError, match="line_identity_subject_unchanged"):
        MySqlLineIdentityRepository(FakeConnection(cursor)).replace_subject(
            LineIdentityClaim(
                LineUserId("U-staff"),
                LineBindingSubjectType.STAFF,
                "staff:7",
            ),
            ExpectedVersion(3),
            "admin:7",
            IdempotencyKey("identity-replace:u-staff:unchanged"),
            "identity-replace:u-staff",
        )


def test_bound_identity_replacement_rejects_cross_type_claim() -> None:
    cursor = ScriptedCursor(
        one_rows=(
            None,
            {"line_user_id": "U-staff"},
            {"admin_count": 0, "nonadmin_count": 1},
            {
                "line_user_id": "U-staff",
                "binding_status": "bound",
                "subject_type": "staff",
                "subject_reference": "staff:7",
                "aggregate_version": 3,
            },
        )
    )

    with pytest.raises(
        RuntimeError,
        match="line_identity_subject_type_change_forbidden",
    ):
        MySqlLineIdentityRepository(FakeConnection(cursor)).replace_subject(
            LineIdentityClaim(
                LineUserId("U-staff"),
                LineBindingSubjectType.CUSTOMER,
                "customer:7",
            ),
            ExpectedVersion(3),
            "admin:7",
            IdempotencyKey("identity-replace:u-staff:cross-type"),
            "identity-replace:u-staff",
        )
