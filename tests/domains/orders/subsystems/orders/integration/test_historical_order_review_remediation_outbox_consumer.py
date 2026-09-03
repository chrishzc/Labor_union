"""
File: test_historical_order_review_remediation_outbox_consumer.py
Description: 驗證歷史訂單 remediation outbox 的 predicate、replay 與 fail-closed 邊界。
"""

from __future__ import annotations

import pytest

from subsystems.orders import historical_order_review_remediation_outbox_consumer as consumer


def _review(identity: str = "prior-review", *, issues=None) -> dict[str, object]:
    return {
        "review_identity": identity,
        "source_event_identity": f"source:{identity}",
        "source_fingerprint": "a" * 64,
        "case_identity": "CA****01",
        "issue_codes": issues if issues is not None else ["staff_missing"],
        "evidence_snapshot": {"evidence": ["phone-log:1"]},
    }


def _orders_snapshot() -> dict[str, object]:
    return {
        "case_no": "CASE-1",
        "status": "completed",
        "lifecycle_version": 3,
        "actual_start_date": "2026-01-01",
        "actual_end_date": "2026-01-31",
        "active_assignments": [
            {
                "assignment_id": 4,
                "staff_id": 8,
                "assignment_sequence": 1,
                "assigned_start_date": "2026-01-01",
                "assigned_end_date": "2026-01-31",
                "status": "completed",
            }
        ],
    }


def _receipt(receipt_id: int, *, identity: str | None, outcome: str) -> dict[str, object]:
    return {
        "id": receipt_id,
        "source_event_identity": f"source:receipt:{receipt_id}",
        "source_fingerprint": "b" * 64,
        "preview_fingerprint": "c" * 64,
        "case_no": "CASE-1",
        "outcome": outcome,
        "review_identity": identity,
        "result_snapshot": {"issue_codes": [] if identity is None else ["staff_missing"]},
    }


def _disposition(*, disposition="corrected_source_adopted", successor=None):
    return {
        "id": 9,
        "event_identity": "event-9",
        "prior_review_identity": "prior-review",
        "original_adoption_receipt_id": 1,
        "replacement_adoption_receipt_id": 2,
        "disposition": disposition,
        "successor_review_identity": successor,
        "source_content_digest": "d" * 64,
        "review_fingerprint": "e" * 64,
        "command_fingerprint": "f" * 64,
        "actor": "operator",
        "reason": "電話確認後重新匯入",
        "evidence_snapshot": {
            "evidence": ["phone-log:1"],
            "orders_terminal_snapshot": _orders_snapshot(),
        },
        "correlation_id": "corr-9",
    }


def test_successor_validation_uses_immutable_review_identity_and_masks_source() -> None:
    disposition = _disposition(
        disposition="superseded_by_replacement_review", successor="successor-review"
    )
    replacement = _receipt(2, identity="successor-review", outcome="review_required")
    successor = _review("successor-review")

    consumer._validate_successor(disposition, replacement, successor, _review())
    assert successor["case_identity"] == "CA****01"
    assert "RAW" not in str(successor)


def test_clean_disposition_requires_adopted_replacement_without_review() -> None:
    consumer._validate_disposition(
        {
            "id": 7,
            "event_id": 9,
            "remediation_receipt_id": 3,
            "bounded_snapshot": consumer._json({
                "orders_terminal_snapshot": _orders_snapshot(),
            }),
        },
        _disposition(),
        {
            "id": 3,
            "event_id": 9,
            "command_fingerprint": "f" * 64,
            "preview_fingerprint": "a" * 64,
            "expected_remediation_version": 0,
            "resulting_remediation_version": 1,
            "result_snapshot": {},
        },
        _review(),
        {**_receipt(1, identity="prior-review", outcome="review_required"), "id": 1},
        {**_receipt(2, identity=None, outcome="adopted"), "id": 2},
    )


class _SnapshotCursor:
    def __init__(self, order: dict[str, object]) -> None:
        self.order = order
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, _params) -> None:
        self.sql = sql

    def fetchone(self):
        return self.order

    def fetchall(self):
        return tuple(self.order["active_assignments"])


class _SnapshotConnection:
    def __init__(self, order: dict[str, object]) -> None:
        self.cursor_value = _SnapshotCursor(order)

    def cursor(self):
        return self.cursor_value


def test_orders_terminal_snapshot_rechecks_locked_root() -> None:
    expected = _orders_snapshot()
    consumer._assert_orders_terminal_snapshot(
        _SnapshotConnection(expected), "CASE-1", expected
    )


def test_post_apply_orders_root_drift_fails_closed_before_projection() -> None:
    drifted = {**_orders_snapshot(), "lifecycle_version": 4}
    with pytest.raises(RuntimeError, match="orders_root_stale"):
        consumer._assert_orders_terminal_snapshot(
            _SnapshotConnection(drifted), "CASE-1", _orders_snapshot()
        )


def test_successor_requires_bound_review_and_review_outcome() -> None:
    disposition = _disposition(
        disposition="superseded_by_replacement_review", successor="successor-review"
    )
    replacement = _receipt(2, identity="successor-review", outcome="review_required")
    successor = _review("successor-review")

    consumer._validate_successor(disposition, replacement, successor, _review())

    with pytest.raises(ValueError, match="successor_issue_codes_missing"):
        consumer._validate_successor(
            disposition,
            replacement,
            _review("successor-review", issues=[]),
            _review(),
        )


def test_consumer_marks_failure_without_claiming_delivery(monkeypatch) -> None:
    class Connection:
        def __init__(self):
            self.rollbacks = 0
            self.commits = 0

        def rollback(self):
            self.rollbacks += 1

        def commit(self):
            self.commits += 1

        def begin(self):
            return None

    connection = Connection()
    event = {"id": 7, "event_id": 9, "bounded_snapshot": "{}"}
    monkeypatch.setattr(consumer, "_claim_next", lambda _connection: event)
    monkeypatch.setattr(consumer, "_load_disposition", lambda *_: (_ for _ in ()).throw(ValueError("bad-event")))
    failed = []
    monkeypatch.setattr(
        consumer,
        "_record_failure",
        lambda _connection, row, error, _runtime: failed.append((row, str(error))),
    )

    assert consumer._consume_next(connection, object()) is False
    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert failed == [(event, "bad-event")]


def test_maximum_events_is_bounded() -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        consumer.consume_historical_order_review_remediation_events(object(), maximum_events=0)
