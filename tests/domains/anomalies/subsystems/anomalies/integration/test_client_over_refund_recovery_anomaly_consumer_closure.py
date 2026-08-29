"""File: test_client_over_refund_recovery_anomaly_consumer_closure.py
Description: 驗證客戶追償異常的 fresh root、狀態 predicate 與失敗閉環。
"""

from datetime import datetime, timezone

import pytest

from shared_kernel.errors import ErrorCategory, TypedError
from subsystems.anomalies import client_over_refund_recovery_anomaly_consumer as consumer
from subsystems.anomalies.root_fact_projection_workflow import RootFactProjectionError


def _event(event_id=7, intent_type="projection_refresh"):
    return {
        "id": event_id,
        "intent_type": intent_type,
        "created_at": datetime(2026, 8, 26, tzinfo=timezone.utc),
    }


def _source(status="open", amount=500):
    return {
        "recovery_identity": "client-recovery:1",
        "case_no": "115000001",
        "finance_import_row_id": 9,
        "batch_id": 3,
        "amount_due_ntd": amount,
        "status": status,
        "recovery_version": 4,
        "account_version": 8,
    }


def test_terminal_root_is_inactive_and_amount_is_fresh_remaining() -> None:
    fact = consumer.build_client_over_refund_recovery_root_fact(
        _event(), _source(status="recovered", amount=0), active=False
    )

    assert fact.active is False
    assert fact.amount_delta_ntd == 0


def test_partial_root_stays_active_with_current_remaining() -> None:
    source = _source(status="partially_recovered", amount=125)
    consumer._validate_source(source)

    assert consumer._event_is_active(_event(), source) is True
    assert consumer.build_client_over_refund_recovery_root_fact(
        _event(), source
    ).amount_delta_ntd == 125


def test_malformed_root_status_fails_closed() -> None:
    with pytest.raises(ValueError, match="root_invalid"):
        consumer._validate_source(_source(status="settled", amount=0))


def test_malformed_event_marker_fails_closed() -> None:
    with pytest.raises(ValueError, match="event_invalid"):
        consumer._event_type(_event(), {"event_type": "not-a-recovery-event"})


class _Cursor:
    def __init__(self, row):
        self.row = row
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_args):
        return None

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.row = row

    def cursor(self):
        return _Cursor(self.row)

    def rollback(self):
        return None

    def commit(self):
        return None


class _RowsConnection(_Connection):
    def __init__(self, *rows):
        self.rows = iter(rows)

    def cursor(self):
        return _Cursor(next(self.rows))


def test_missing_root_fails_closed() -> None:
    with pytest.raises(ValueError, match="root_not_found"):
        consumer._load_source(
            _Connection(None),
            _event(),
            {"event_type": "client_over_refund_recovery_established", "recovery_identity": "missing"},
        )


def test_matching_source_uses_incoming_bank_row_for_action_binding() -> None:
    source = {
        **_source(),
        "finance_import_row_id": 99,
        "matching_identity": "match:1",
        "matching_version": 1,
    }
    loaded = consumer._load_source(
        _Connection(source),
        _event(intent_type="client_over_refund_recovery_matched"),
        {"recovery_identity": source["recovery_identity"], "matching_identity": "match:1"},
    )

    assert loaded["finance_import_row_id"] == 99
    assert loaded["matching_identity"] == "match:1"


@pytest.mark.parametrize(
    "intent_type",
    ["projection_refresh", "client_over_refund_recovery_collected"],
)
def test_updated_or_collected_matching_uses_incoming_row(
    intent_type: str,
) -> None:
    root = _source()
    matching = {
        "matching_identity": "match:1",
        "matching_version": 1,
        "recovery_identity": root["recovery_identity"],
        "case_no": root["case_no"],
        "finance_import_row_id": 99,
        "batch_id": 8,
    }
    payload = {
        "recovery_identity": root["recovery_identity"],
        "matching_identity": matching["matching_identity"],
    }
    if intent_type == "projection_refresh":
        payload["event_type"] = "client_over_refund_recovery_updated"
    event = _event(intent_type=intent_type)
    loaded = consumer._load_source(
        _RowsConnection(root, matching), event, payload
    )

    assert loaded["finance_import_row_id"] == 99
    assert loaded["batch_id"] == 8
    assert loaded["matching_identity"] == "match:1"


def test_late_projection_failure_is_acked_without_projection_rollback(monkeypatch) -> None:
    event = {**_event(4), "payload_snapshot": {"event_type": "client_over_refund_recovery_updated", "recovery_identity": "client-recovery:1"}}
    source = _source()

    class _LateApplication:
        def __init__(self, *_args):
            pass

        def project(self, *_args):
            raise RootFactProjectionError(
                TypedError(
                    ErrorCategory.CONFLICT,
                    "anomaly_projection_stale",
                    "late event",
                    None,
                )
            )

    class _EventConnection(_Connection):
        def __init__(self):
            self.rows = iter([event, source, {"ok": True}])

        def cursor(self):
            return _Cursor(next(self.rows))

    monkeypatch.setattr(consumer, "RootFactProjectionApplication", _LateApplication)

    assert consumer.consume_client_over_refund_recovery_anomaly_events(
        _EventConnection(), maximum_events=1
    ) == (1, 0)
