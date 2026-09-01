"""Contract tests for the MySQL historical completion lifecycle adapter."""

from datetime import date

from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.historical_completion_writer import (
    MySqlHistoricalCompletionWriter,
    _child_identity,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.historical_completion_apply import (
    ApplyHistoricalCompletion,
    HistoricalCompletionCandidate,
)


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Connection:
    def cursor(self):
        return _Cursor()


def _candidate():
    return HistoricalCompletionCandidate(
        "CASE-1",
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
        7,
        8,
        4,
        (),
        date(2026, 8, 20),
        date(2026, 9, 1),
        PreviewFingerprint("a" * 64),
        PreviewFingerprint("b" * 64),
    )


def _request():
    return ApplyHistoricalCompletion(
        "CASE-1",
        7,
        4,
        (),
        PreviewFingerprint("b" * 64),
        IdempotencyKey("historical-completion:key-1"),
        ActorContext("admin"),
        "雙邊款項已核實結清",
        CorrelationId("historical-completion:test"),
    )


def test_persist_reuses_canonical_event_outbox_and_projection_writers(monkeypatch) -> None:
    calls = []

    def persist_event(cursor, command):
        calls.append(("event", command))
        return 91

    def persist_projection(cursor, command):
        calls.append(("projection", command))

    monkeypatch.setattr(
        "infrastructure.mysql.historical_completion_writer.persist_order_lifecycle_impact",
        persist_event,
    )
    monkeypatch.setattr(
        "infrastructure.mysql.historical_completion_writer.persist_order_lifecycle_projection",
        persist_projection,
    )

    receipt = MySqlHistoricalCompletionWriter(_Connection()).persist(
        _request(), _candidate()
    )

    assert [name for name, _ in calls] == ["event", "projection"]
    command = calls[0][1]
    assert command.trigger_event == "historical_accounting_settled"
    assert command.candidate.actual_end_date == date(2026, 8, 20)
    assert command.candidate.after_status is OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED
    assert receipt.lifecycle_event_id == 91
    assert receipt.resulting_order_version == 8


def test_event_replay_identity_matches_canonical_orders_writer_contract() -> None:
    key = IdempotencyKey("historical-completion:key-1")

    assert _child_identity(key, "lifecycle-event").startswith("child:")
    assert _child_identity(key, "lifecycle-event") == _child_identity(
        key, "lifecycle-event"
    )
