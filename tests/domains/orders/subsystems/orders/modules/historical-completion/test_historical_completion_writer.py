"""Contract tests for the MySQL historical completion lifecycle adapter."""

import json
from datetime import date

import pytest

from domains.orders.lifecycle import LifecycleImpactCandidate, OrderLifecycleStatus
from infrastructure.mysql.historical_completion_writer import (
    MySqlHistoricalCompletionWriter,
    MySqlHistoricalServiceCompletionWriter,
    _child_identity,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.historical_completion_apply import (
    ApplyHistoricalServiceCompletion,
    ApplyHistoricalCompletion,
    HistoricalCompletionCandidate,
    HistoricalPayrollSyncResult,
    HistoricalServiceCompletionCandidate,
)
class _Cursor:
    def __init__(self):
        self.calls = []
        self.lastrowid = 92
        self.rowcount = 1
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))

    def fetchall(self):
        return ()

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self):
        self.cursor_value = _Cursor()

    def cursor(self):
        return self.cursor_value


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


def test_apply_locks_historical_staff_payout_roots() -> None:
    connection = _Connection()

    MySqlHistoricalCompletionWriter(connection)._lock_owner_roots("CASE-1")

    statements = tuple(statement for statement, _ in connection.cursor_value.calls)
    assert any("FROM historical_staff_payout_projections" in item for item in statements)
    assert any("FROM historical_staff_payout_obligation_links" in item for item in statements)
    assert any("FROM historical_staff_payout_events" in item for item in statements)
    assert all(parameters == ("CASE-1",) for _, parameters in connection.cursor_value.calls)


@pytest.mark.parametrize("payroll_result", (
    {"action": "created"},
    {"action": "skipped", "reason": "payroll_rate_policy_not_found", "detail": "請查核月嫂時薪。"},
))
def test_service_completion_keeps_payroll_outcome_in_event_and_receipt(monkeypatch, payroll_result) -> None:
    connection = _Connection()
    cursor = connection.cursor_value

    def synchronize_payroll(connection, case_no, **kwargs):
        assert [sql.split(maxsplit=2)[:2] for sql, _ in cursor.calls] == [["UPDATE", "orders"]]
        assert cursor.calls[0][1][0] == OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value
        return payroll_result

    def synchronize_subsidy(cursor, case_no, *, source_id, **kwargs):
        assert source_id == 92
        assert "orders_domain_outbox" in cursor.calls[-1][0]

    monkeypatch.setattr(
        "infrastructure.mysql.automatic_client_accounting.synchronize_terminal_subsidy_return",
        synchronize_subsidy,
    )
    lifecycle = LifecycleImpactCandidate(
        "CASE-1",
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        date(2026, 9, 21),
        None,
        date(2026, 9, 22),
        True,
        False,
        False,
        (),
        PreviewFingerprint("c" * 64),
    )
    candidate = HistoricalServiceCompletionCandidate(
        lifecycle, 7, 8, "historical-source:CASE-1"
    )
    request = ApplyHistoricalServiceCompletion(
        "CASE-1",
        7,
        date(2026, 9, 22),
        IdempotencyKey("historical-service-completion:key-1"),
        ActorContext("system:historical-service-completion"),
        "historical source service end date passed",
        CorrelationId("historical-service-completion:test"),
    )

    monkeypatch.setattr(
        "subsystems.payroll.historical_baseline_obligation_sync.synchronize_historical_payroll",
        synchronize_payroll,
    )
    writer = MySqlHistoricalServiceCompletionWriter(connection)
    receipt = writer.persist_service_completion(request, candidate)

    _, event = cursor.calls[1]
    assert event[1] == "historical_service_period_elapsed"
    snapshot = json.loads(event[-1])
    assert snapshot["service_data_lock_should_exist"] is False
    assert snapshot["historical_payroll_sync"] == payroll_result
    assert json.loads(cursor.calls[2][1][-1]) == snapshot
    assert receipt.lifecycle_event_id == 92
    assert receipt.after_status is OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED
    assert receipt.payroll_sync == HistoricalPayrollSyncResult(**payroll_result)

    cursor.row = {
        "command_fingerprint": "c" * 64, "id": 92, "case_no": "CASE-1",
        "after_status": receipt.after_status.value, "expected_version": 7,
        "payroll_action": payroll_result["action"], "payroll_reason": payroll_result.get("reason"),
        "payroll_detail": payroll_result.get("detail"),
    }
    assert writer.find_service_completion_receipt(request.idempotency_key).receipt == receipt
    cursor.row["payroll_action"] = None
    assert writer.find_service_completion_receipt(request.idempotency_key).receipt.payroll_sync is None
