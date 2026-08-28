"""
File: test_staff_overpayment_recovery_anomaly_consumer.py
Description: 驗證 Staff recovery outbox claim、fresh projection 與 fail-closed 契約。
"""

from datetime import datetime, timezone

import pytest

from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
import subsystems.anomalies.staff_overpayment_recovery_anomaly_consumer as consumer
from subsystems.anomalies.staff_overpayment_recovery_anomaly_consumer import (
    _bank_ids,
    _claim,
    _event_type,
    _failed,
    _source as load_source,
    build_staff_overpayment_recovery_root_fact,
)
from subsystems.anomalies.root_fact_projection_workflow import RootFactProjectionError


def _event(event_type, event_id=7):
    return {
        "id": event_id,
        "intent_type": "staff_overpayment_recovery_updated"
        if event_type == "staff_overpayment_recovery_established"
        else event_type,
        "created_at": datetime(2026, 8, 26, tzinfo=timezone.utc),
    }


def _source(status="open", remaining=1000):
    return {
        "recovery_identity": "recovery:1",
        "staff_id": 7,
        "remaining_amount_ntd": remaining,
        "status": status,
        "recovery_version": 0 if status == "open" else 2,
        "staff_payables_version": 4,
        "finance_import_row_id": 11,
        "finance_import_batch_id": 3,
    }


@pytest.mark.parametrize(
    ("event_type", "status", "remaining", "active"),
    [
        ("staff_overpayment_recovery_established", "open", 1000, True),
        ("staff_overpayment_recovery_matched", "open", 1000, True),
        ("staff_overpayment_recovery_updated", "partially_recovered", 400, True),
        ("staff_overpayment_recovery_collected", "recovered", 0, False),
        ("staff_overpayment_recovery_updated", "adjusted", 0, False),
    ],
)
def test_root_fact_uses_fresh_recovery_status_and_remaining(
    event_type, status, remaining, active
):
    root = build_staff_overpayment_recovery_root_fact(
        _event(event_type), _source(status, remaining), event_type=event_type
    )

    assert root.active is active
    assert root.amount_delta_ntd == remaining
    assert root.source_identity == "staff-overpayment-recovery:recovery:1"


def test_established_payload_can_use_existing_outbox_enum_without_intent_alias():
    event = _event("staff_overpayment_recovery_established")

    assert _event_type(
        event,
        {
            "event_type": "staff_overpayment_recovery_established",
            "recovery_identity": "recovery:1",
        },
    ) == "staff_overpayment_recovery_established"


@pytest.mark.parametrize(
    "event,payload",
    [
        ({"id": 1, "intent_type": "unknown"}, {}),
        ({"id": 1, "intent_type": "staff_overpayment_recovery_matched"}, {"event_type": "staff_overpayment_recovery_updated"}),
        ({"id": 1, "intent_type": "staff_overpayment_recovery_matched"}, {"event_type": "staff_overpayment_recovery_established"}),
    ],
)
def test_malformed_event_type_fails_closed(event, payload):
    with pytest.raises(ValueError):
        _event_type(event, payload)


class _MissingRootCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        return None

    def fetchone(self):
        return None


class _MissingRootConnection:
    def cursor(self):
        return _MissingRootCursor()


def test_missing_recovery_root_fails_closed():
    with pytest.raises(ValueError, match="root_not_found"):
        load_source(_MissingRootConnection(), {"recovery_identity": "missing"})


class _ClaimCursor:
    def __init__(self, event):
        self.event = event
        self.statement = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, *_):
        self.statement = statement

    def fetchone(self):
        return self.event


class _ClaimConnection:
    def __init__(self, event):
        self.cursor_instance = _ClaimCursor(event)

    def cursor(self):
        return self.cursor_instance


def test_claim_targets_established_payload_intent_and_bounded_retry_filter():
    connection = _ClaimConnection({"id": 7})

    assert _claim(connection) == {"id": 7}
    assert "staff_overpayment_recovery_established" not in connection.cursor_instance.statement
    assert "staff_overpayment_recovery_updated" in connection.cursor_instance.statement
    assert "attempt_count<3" in connection.cursor_instance.statement


class _ConsumeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_consume_established_event_projects_fresh_successor_and_acknowledges(monkeypatch):
    event = {
        "id": 7,
        "intent_type": "staff_overpayment_recovery_updated",
        "payload_snapshot": {
            "event_type": "staff_overpayment_recovery_established",
            "recovery_identity": "recovery:1",
        },
        "created_at": datetime(2026, 8, 26, tzinfo=timezone.utc),
    }
    pending = iter((event, None))
    projected = []
    delivered = []
    connection = _ConsumeConnection()
    monkeypatch.setattr(consumer, "_claim", lambda _connection: next(pending))
    monkeypatch.setattr(consumer, "_source", lambda _connection, _payload: _source())
    monkeypatch.setattr(consumer, "_project", lambda _connection, _event, root: projected.append(root))
    monkeypatch.setattr(consumer, "_delivered", lambda _connection, event_id: delivered.append(event_id))

    assert consumer.consume_staff_overpayment_recovery_anomaly_events(connection) == (1, 0)
    assert delivered == [7]
    assert projected[0].source_identity == "staff-overpayment-recovery:recovery:1"
    assert projected[0].active is True
    assert projected[0].amount_delta_ntd == 1000
    assert connection.commits == 1


def test_bank_fact_identity_uses_canonical_bank_prefix():
    assert _bank_ids(["finance-import-row:1"]) == (1,)
    with pytest.raises(ValueError):
        _bank_ids(["bank:1"])


@pytest.mark.parametrize(
    ("status", "remaining"),
    [("open", 0), ("partially_recovered", 0), ("recovered", 1), ("adjusted", 1)],
)
def test_terminal_and_active_status_mismatch_fails_closed(status, remaining):
    with pytest.raises(ValueError, match="inconsistent"):
        build_staff_overpayment_recovery_root_fact(
            _event("staff_overpayment_recovery_updated"),
            _source(status, remaining),
            event_type="staff_overpayment_recovery_updated",
        )


def test_late_projection_event_is_acknowledged_without_reverting_current_alert(monkeypatch):
    class _StaleApplication:
        def __init__(self, *_args):
            pass

        def project(self, *_args):
            raise RootFactProjectionError(
                TypedError(
                    ErrorCategory.CONFLICT,
                    "anomaly_projection_stale",
                    "stale projection",
                    CorrelationId("staff-recovery-test"),
                )
            )

    monkeypatch.setattr(consumer, "RootFactProjectionApplication", _StaleApplication)
    consumer._project(
        object(),
        {"id": 2},
        object(),
    )


class _RaceCursor:
    rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        return None


class _RaceConnection:
    def cursor(self):
        return _RaceCursor()

    def commit(self):
        raise AssertionError("must not commit a failed status race")


def test_failed_ack_does_not_overwrite_delivered_outbox():
    with pytest.raises(RuntimeError, match="failure_conflict"):
        _failed(_RaceConnection(), 9)
