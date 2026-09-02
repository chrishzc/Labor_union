from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from domains.orders.historical_adoption import (
    HistoricalOrderOutcome,
    HistoricalOrderSourceStatus,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.historical_order_adoption_repository import (
    _operational_baseline_snapshot,
)
from infrastructure.mysql.historical_stage_baseline_repository import _facts


def test_formal_baseline_event_wins_over_later_order_status() -> None:
    facts = _facts(
        {
            "case_no": "CASE-1",
            "status": OrderLifecycleStatus.COMPLETED.value,
            "actual_start_date": date(2026, 8, 8),
            "adoption_receipt_id": 31,
            "adoption_result_snapshot": {
                "historical_source_status": "deposit_paid",
                "operational_baseline_step": 9,
                "operational_baseline_actual_start_date": None,
            },
            "adoption_after_status": OrderLifecycleStatus.ESTABLISHED.value,
            "adoption_facts_snapshot": {},
            "baseline_event_version": 81,
            "baseline_event_identity": "historical-operational-baseline-event:immutable",
            "selected_step": 10,
        }
    )

    assert facts.lifecycle_status is OrderLifecycleStatus.ESTABLISHED
    assert facts.selected_step == 10
    assert facts.baseline_event_identity == "historical-operational-baseline-event:immutable"
    assert facts.baseline_event_version == 81


def test_legacy_adoption_event_keeps_original_step_after_current_status_moves() -> None:
    facts = _facts(
        {
            "case_no": "CASE-1",
            "status": OrderLifecycleStatus.COMPLETED.value,
            "actual_start_date": date(2026, 8, 8),
            "adoption_receipt_id": 32,
            "adoption_result_snapshot": {"outcome": "adopted"},
            "adoption_after_status": OrderLifecycleStatus.ESTABLISHED.value,
            "adoption_facts_snapshot": {
                "date_patch": (("actual_start_date", "2026-08-08"),)
            },
            "baseline_event_version": None,
            "baseline_event_identity": None,
            "selected_step": None,
        }
    )

    assert facts.lifecycle_status is OrderLifecycleStatus.ESTABLISHED
    assert facts.actual_start_date == date(2026, 8, 8)
    assert facts.selected_step == 10


def test_new_adoption_receipt_freezes_deposit_paid_actual_start_baseline() -> None:
    request = SimpleNamespace(
        row=SimpleNamespace(asserted_status=HistoricalOrderSourceStatus.DEPOSIT_PAID)
    )
    preview = SimpleNamespace(
        outcome=HistoricalOrderOutcome.ADOPTED,
        after_status=OrderLifecycleStatus.ESTABLISHED.value,
        date_patch=(("actual_start_date", date(2026, 8, 9)),),
    )

    snapshot = _operational_baseline_snapshot(request, preview)

    assert snapshot == {
        "historical_source_status": "deposit_paid",
        "operational_baseline_step": 10,
        "operational_baseline_actual_start_date": "2026-08-09",
    }


def test_old_null_step_receipts_recover_from_adoption_event_status() -> None:
    expected = {
        OrderLifecycleStatus.HISTORICAL_UNSERVED: 9,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE: 10,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED: 11,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED: 11,
    }
    for status, step in expected.items():
        facts = _facts(
            {
                "case_no": f"CASE-{step}",
                "status": status.value,
                "actual_start_date": date(2026, 8, 8),
                "adoption_receipt_id": step,
                "adoption_result_snapshot": {
                    "historical_source_status": "deposit_paid",
                    "operational_baseline_step": None,
                    "operational_baseline_actual_start_date": None,
                },
                "adoption_after_status": status.value,
                "adoption_facts_snapshot": {},
                "baseline_event_version": None,
                "baseline_event_identity": None,
                "selected_step": None,
            }
        )
        assert facts.selected_step == step


def test_new_adoption_snapshot_maps_historical_lifecycle_statuses() -> None:
    request = SimpleNamespace(
        row=SimpleNamespace(asserted_status=HistoricalOrderSourceStatus.DEPOSIT_PAID)
    )
    expected = {
        OrderLifecycleStatus.HISTORICAL_UNSERVED: 9,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE: 10,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED: 11,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED: 11,
    }
    for status, step in expected.items():
        preview = SimpleNamespace(
            outcome=HistoricalOrderOutcome.ADOPTED,
            after_status=status.value,
            date_patch=(("actual_start_date", date(2026, 8, 9)),),
        )
        assert _operational_baseline_snapshot(request, preview)["operational_baseline_step"] == step


def test_new_adoption_receipt_freezes_plain_deposit_paid_at_step_nine() -> None:
    request = SimpleNamespace(
        row=SimpleNamespace(asserted_status=HistoricalOrderSourceStatus.DEPOSIT_PAID)
    )
    preview = SimpleNamespace(
        outcome=HistoricalOrderOutcome.ADOPTED,
        after_status=OrderLifecycleStatus.ESTABLISHED.value,
        date_patch=(),
    )

    snapshot = _operational_baseline_snapshot(request, preview)

    assert snapshot["operational_baseline_step"] == 9
    assert snapshot["operational_baseline_actual_start_date"] is None
