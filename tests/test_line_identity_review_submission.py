"""Characterize LINE identity-review request submission."""

import pytest

from subsystems.line import identity_review_workflow
from subsystems.line.client_binding_application import (
    LegacyClientBindingRetiredError,
    bind_client,
)


class _Cursor:
    lastrowid = 41

    def __init__(self) -> None:
        self.statements: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters=None) -> None:
        self.statements.append((" ".join(statement.split()), parameters))


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()
        self.commits = 0

    def begin(self) -> None:
        return None

    def cursor(self, *_):
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        raise AssertionError("valid staff verification must not roll back")

    def close(self) -> None:
        return None


def test_submit_staff_verification_is_retired_before_read_or_write(monkeypatch):
    connection = _Connection()
    queued: list[dict] = []
    monkeypatch.setattr(identity_review_workflow, "get_connection", lambda: connection)

    with pytest.raises(identity_review_workflow.LegacyLineReviewRetiredError):
        identity_review_workflow.submit_staff_verification(
            "U-staff",
            source_event_id="event-1",
            delivery_callback=queued.append,
        )

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert statements == []
    assert queued == []
    assert connection.commits == 0


def test_submit_client_rebind_is_retired_before_write(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(identity_review_workflow, "get_connection", lambda: connection)

    with pytest.raises(identity_review_workflow.LegacyLineReviewRetiredError):
        identity_review_workflow.submit_client_rebind_request_in_transaction(
            connection.cursor_instance,
            client_id=17,
            client_name="王小美",
            old_line_user_id="U-old",
            new_line_user_id="U-new",
        )

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert statements == []
    assert connection.commits == 0


def test_complete_client_binding_is_retired_without_canonical_apply_context():
    cursor = _Cursor()

    with pytest.raises(identity_review_workflow.LegacyLineReviewRetiredError):
        identity_review_workflow.complete_client_binding_in_transaction(
            cursor,
            client_id=17,
            client_name="王小美",
            case_no="C-2026-01",
            current_line_user_id="",
            line_user_id="U-client",
        )

    statements = [statement for statement, _ in cursor.statements]
    assert statements == []


def test_legacy_client_binding_wrapper_fails_closed_before_read_or_write():
    connection = _Connection()

    with pytest.raises(LegacyClientBindingRetiredError):
        bind_client(
            connection,
            name="王小美",
            phone="0912-345-678",
            line_user_id="U-client",
            force_rebind=False,
        )

    assert connection.cursor_instance.statements == []
    assert connection.commits == 0
