"""
File: tests/test_order_lifecycle_authoritative_facts.py
Description: 驗證訂單生命週期事實格式與待補件狀態的可辨識性。
"""

from datetime import datetime, timezone

import pytest

from subsystems.orders.lifecycle_authoritative_facts import validate_order_lifecycle_facts
from subsystems.orders.order_lifecycle_command_envelope import _validate_order_row


def _facts(**changes):
    value = {"cancellation": False, "cancellation_reason": None, "deposit_reconciled": True, "deposit_settlement_identity": "a" * 64, "actual_start_date": "2026-08-01", "actual_end_date": None, "evaluation_at": "2026-08-01T00:00:00+00:00", "completion_instant": None, "completion_facts_consistent": True, "actual_start_reconfirmed": True, "effective_scheduling_generation_id": 1, "official_service_dates": ("2026-08-01",), "transition_blockers": {"enter_service": (), "auto_complete": ()}, "manual_correction_target": None}
    value.update(changes)
    return value


def test_validates_exact_canonical_lifecycle_facts_schema():
    result = validate_order_lifecycle_facts("訂單成立", "deposit_reconciled", _facts())
    assert result.validated_facts.evaluation_at.tzinfo is not None
    assert result.validated_facts.deposit_settlement_identity == "a" * 64


def test_accepts_pending_completion_as_a_formal_nonservice_status():
    result = validate_order_lifecycle_facts("待補件", "case_created", _facts())

    assert result.validated_status == "待補件"


def test_pending_completion_order_is_rejected_before_lifecycle_command_processing():
    pending_order = {
        "case_no": "CASE-PENDING",
        "status": "待補件",
        "lifecycle_version": 0,
        "service_days": None,
        "cancel_reason": None,
        "actual_start_date": None,
        "actual_end_date": None,
        "service_start_time": None,
        "service_end_time": None,
        "service_end_day_offset": None,
    }

    with pytest.raises(ValueError, match="pending-completion"):
        _validate_order_row(pending_order, "CASE-PENDING")


@pytest.mark.parametrize("change", [{"unexpected": True}, {"transition_blockers": {"enter_service": ("bad code",), "auto_complete": ()}}, {"cancellation": True}, {"deposit_settlement_identity": "A" * 64}])
def test_rejects_noncanonical_lifecycle_facts(change):
    with pytest.raises((TypeError, ValueError)):
        validate_order_lifecycle_facts("訂單成立", "deposit_reconciled", _facts(**change))


def test_manual_correction_requires_a_target():
    with pytest.raises(ValueError, match="requires"):
        validate_order_lifecycle_facts("訂單成立", "manual_correction", _facts())


def test_requires_sorted_unique_official_service_dates():
    with pytest.raises(ValueError, match="official_service_dates"):
        validate_order_lifecycle_facts(
            "服務中",
            "evaluation_time_reached",
            _facts(
                effective_scheduling_generation_id=7,
                official_service_dates=("2026-08-02", "2026-08-01"),
            ),
        )


def test_completion_consistency_requires_effective_service_roots():
    with pytest.raises(ValueError, match="completion-consistent"):
        validate_order_lifecycle_facts(
            "服務中",
            "evaluation_time_reached",
            _facts(effective_scheduling_generation_id=None),
        )
