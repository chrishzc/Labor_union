"""
File: test_government_overpayment_anomaly_consumer.py
Description: 驗證 GOVSUB-006 依 fresh overpayment disposition root 投影。
"""

from datetime import datetime, timezone

import pytest

from subsystems.anomalies.government_overpayment_anomaly_consumer import (
    build_government_overpayment_root_fact,
    _root_fact_for_event,
)


def test_government_overpayment_event_builds_bound_govsub_root_fact() -> None:
    fact = build_government_overpayment_root_fact(
        {"id": 9, "batch_id": 4, "intent_type": "government_subsidy_overpayment_established", "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc), "payload_snapshot": {"overpayment_identity": "over-1"}},
        {
            "finance_import_row_id": 7,
            "finance_import_batch_id": 3,
            "projection_version": 1,
            "payer_identity": "hccg",
            "remaining_amount_ntd": 500,
            "status": "pending_review",
        },
    )
    assert fact.definition_code == "GOVSUB-006"
    assert fact.active is True
    assert fact.amount_delta_ntd == 500
    assert dict(fact.recovery_bindings) == {"overpayment_identity": "over-1", "overpayment_version": 1}


def test_government_overpayment_root_fact_uses_canonical_bank_batch_not_claim_batch() -> None:
    fact = build_government_overpayment_root_fact(
        {"id": 9, "batch_id": 999, "intent_type": "government_subsidy_overpayment_established", "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc), "payload_snapshot": {"overpayment_identity": "over-1"}},
        {
            "finance_import_row_id": 7,
            "finance_import_batch_id": 3,
            "projection_version": 1,
            "payer_identity": "hccg",
            "remaining_amount_ntd": 500,
            "status": "pending_review",
        },
    )

    assert fact.finance_import_batch_id == 3


@pytest.mark.parametrize(
    "intent,status,active",
    [
        ("government_subsidy_overpayment_established", "pending_review", True),
        ("government_subsidy_overpayment_offset", "offset_reserved", False),
        ("government_overpayment_return_payable", "return_payable", False),
    ],
)
def test_disposition_events_use_fresh_status_and_remaining(
    intent: str, status: str, active: bool
) -> None:
    fact = build_government_overpayment_root_fact(
        {
            "id": 10,
            "intent_type": intent,
            "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
            "payload_snapshot": {
                "overpayment_identity": "over-1",
                "amount_ntd": 999999,
            },
        },
        {
            "finance_import_row_id": 7,
            "finance_import_batch_id": 3,
            "projection_version": 4,
            "payer_identity": "hccg",
            "remaining_amount_ntd": 275,
            "status": status,
        },
    )
    assert fact.active is active
    assert fact.amount_delta_ntd == 275
    assert fact.source_version == 10
    assert fact.source_event_identity == "government-overpayment:over-1:10"


def test_late_event_keeps_stable_alert_identity_and_event_version() -> None:
    fact = build_government_overpayment_root_fact(
        {
            "id": 8,
            "intent_type": "government_subsidy_overpayment_established",
            "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
            "payload_snapshot": {"overpayment_identity": "over-1"},
        },
        {
            "finance_import_row_id": 7,
            "finance_import_batch_id": 3,
            "projection_version": 2,
            "payer_identity": "hccg",
            "remaining_amount_ntd": 500,
            "status": "pending_review",
        },
    )
    assert fact.source_version == 8
    assert fact.source_identity == "government-overpayment:over-1"


@pytest.mark.parametrize(
    "event,source,error",
    [
        (
            {
                "id": 1,
                "intent_type": "unexpected",
                "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
                "payload_snapshot": {"overpayment_identity": "over-1"},
            },
            {},
            "government_overpayment_event_not_projectable",
        ),
        (
            {
                "id": 1,
                "intent_type": "government_subsidy_overpayment_offset",
                "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
                "payload_snapshot": {"overpayment_identity": "over-1"},
            },
            {
                "finance_import_row_id": 7,
                "finance_import_batch_id": 3,
                "projection_version": 2,
                "payer_identity": "hccg",
                "remaining_amount_ntd": 1,
                "status": "unknown",
            },
            "government overpayment status is invalid",
        ),
    ],
)
def test_malformed_event_or_root_fails_closed(event, source, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        build_government_overpayment_root_fact(event, source)


def test_missing_current_overpayment_root_fails_closed() -> None:
    connection = _Connection(None)
    event = {
        "id": 11,
        "intent_type": "government_subsidy_overpayment_offset",
        "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
        "payload_snapshot": {"overpayment_identity": "missing"},
    }
    with pytest.raises(ValueError, match="government_subsidy_overpayment_not_found"):
        _root_fact_for_event(connection, event, event["payload_snapshot"])


def test_wrong_government_payer_fails_closed() -> None:
    event = {
        "id": 12,
        "intent_type": "government_subsidy_overpayment_offset",
        "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
        "payload_snapshot": {"overpayment_identity": "over-1"},
    }
    with pytest.raises(ValueError, match="government_subsidy_overpayment_payer_invalid"):
        build_government_overpayment_root_fact(
            event,
            {
                "finance_import_row_id": 7,
                "finance_import_batch_id": 3,
                "projection_version": 2,
                "payer_identity": "other-government",
                "remaining_amount_ntd": 1,
                "status": "pending_review",
            },
        )


@pytest.mark.parametrize(
    ("status", "remaining"),
    [
        ("pending_review", 0),
        ("offset_reserved", 0),
        ("return_payable", 0),
        ("partially_returned", 0),
        ("offset_applied", 1),
        ("returned", 1),
    ],
)
def test_status_remaining_invariant_fails_closed(status: str, remaining: int) -> None:
    with pytest.raises(ValueError, match="government_overpayment_status_remaining_invalid"):
        build_government_overpayment_root_fact(
            {
                "id": 13,
                "intent_type": "government_subsidy_overpayment_offset",
                "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
                "payload_snapshot": {"overpayment_identity": "over-1"},
            },
            {
                "finance_import_row_id": 7,
                "finance_import_batch_id": 3,
                "projection_version": 2,
                "payer_identity": "hccg",
                "remaining_amount_ntd": remaining,
                "status": status,
            },
        )


class _Connection:
    def __init__(self, row) -> None:
        self.row = row

    def cursor(self):
        return _Cursor(self.row)


class _Cursor:
    def __init__(self, row) -> None:
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args):
        return None

    def fetchone(self):
        return self.row
