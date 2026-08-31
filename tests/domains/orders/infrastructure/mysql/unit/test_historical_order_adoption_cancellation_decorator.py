from types import SimpleNamespace

from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql import historical_order_adoption_cancellation_decorator as module


class _Cursor:
    def __init__(self, current=None):
        self.current = current
        self.executed = []

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.current

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def __init__(self, current=None):
        self.cursor_instance = _Cursor(current)

    def cursor(self):
        return self.cursor_instance


def _preview(after_status):
    return SimpleNamespace(
        case_no="CASE-1",
        after_status=after_status,
        expected_version=4,
        resulting_version=5,
    )


def _request():
    return SimpleNamespace(
        actor="historical-import",
        reason="資料匯入中心訂單歷史採納",
        idempotency_key="historical-row-1",
    )


def test_status_zero_activates_existing_cancellation_control_contract(monkeypatch) -> None:
    connection = _Connection(None)
    envelope = object()
    commands = []
    monkeypatch.setattr(
        module,
        "lock_order_lifecycle_command_envelope",
        lambda *_args: envelope,
    )
    monkeypatch.setattr(
        module,
        "apply_order_lifecycle_control_command",
        lambda _cursor, actual_envelope, command: commands.append(
            (actual_envelope, command)
        ),
    )

    module._sync_historical_cancellation(
        connection,
        _request(),
        _preview(OrderLifecycleStatus.CANCELLED.value),
    )

    assert len(commands) == 1
    assert commands[0][0] is envelope
    assert commands[0][1].action == "activate"
    assert commands[0][1].reason.startswith("historical_order_adoption:")


def test_non_mutating_adoption_does_not_create_control_only_history(monkeypatch) -> None:
    connection = _Connection(None)
    called = False

    def _unexpected(*_args):
        nonlocal called
        called = True

    monkeypatch.setattr(module, "lock_order_lifecycle_command_envelope", _unexpected)
    preview = _preview(OrderLifecycleStatus.CANCELLED.value)
    preview.resulting_version = preview.expected_version

    module._sync_historical_cancellation(connection, _request(), preview)

    assert called is False
