"""Characterize LINE identity-review request submission."""

from subsystems.line import identity_review_workflow


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


def test_submit_staff_verification_replaces_pending_request_and_queues_reply(monkeypatch):
    connection = _Connection()
    queued: list[dict] = []
    monkeypatch.setattr(identity_review_workflow, "get_connection", lambda: connection)
    monkeypatch.setattr(
        identity_review_workflow,
        "_template",
        lambda _template_id, fallback: fallback,
    )
    monkeypatch.setattr(
        identity_review_workflow,
        "enqueue_line_task",
        lambda _cursor, **kwargs: queued.append(kwargs),
    )

    result = identity_review_workflow.submit_staff_verification(
        "U-staff",
        source_event_id="event-1",
    )

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert result == {"request_id": 41, "worker_wakeup_required": True}
    assert any("UPDATE line_confirmation_requests SET status='cancelled'" in statement for statement in statements)
    assert any("INSERT INTO line_confirmation_requests (request_type, line_user_id)" in statement for statement in statements)
    assert queued == [{
        "to_user_id": "U-staff",
        "message_content": "月嫂身分申請已送出，請等待工會人員確認。",
        "source_event_id": "event-1",
        "idempotency_key": "staff-verification-request:41",
    }]
    assert connection.commits == 1


def test_submit_client_rebind_replaces_pending_request(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(identity_review_workflow, "get_connection", lambda: connection)

    result = identity_review_workflow.submit_client_rebind_request_in_transaction(
        connection.cursor_instance,
        client_id=17,
        client_name="王小美",
        old_line_user_id="U-old",
        new_line_user_id="U-new",
    )

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert result == {"request_id": 41, "worker_wakeup_required": True}
    assert any("UPDATE line_confirmation_requests SET status='cancelled'" in statement for statement in statements)
    assert any("INSERT INTO line_confirmation_requests ( request_type, line_user_id, client_id, client_name," in statement for statement in statements)
    assert connection.commits == 0


def test_complete_client_binding_updates_identity_and_queues_confirmation(monkeypatch):
    cursor = _Cursor()
    queued: list[dict] = []
    monkeypatch.setattr(
        identity_review_workflow,
        "enqueue_line_task",
        lambda _cursor, **kwargs: queued.append(kwargs),
    )

    result = identity_review_workflow.complete_client_binding_in_transaction(
        cursor,
        client_id=17,
        client_name="王小美",
        case_no="C-2026-01",
        current_line_user_id="",
        line_user_id="U-client",
    )

    statements = [statement for statement, _ in cursor.statements]
    assert result == {"worker_wakeup_required": True}
    assert any("UPDATE clients SET line_user_id = %s WHERE id = %s" in statement for statement in statements)
    assert not any("INSERT INTO orders" in statement for statement in statements)
    assert queued[0]["to_user_id"] == "U-client"
    assert "C-2026-01" in queued[0]["message_content"]
