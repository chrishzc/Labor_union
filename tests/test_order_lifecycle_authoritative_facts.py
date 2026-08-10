from datetime import datetime, timezone

import pytest

from subsystems.orders.lifecycle_authoritative_facts import validate_order_lifecycle_facts


def _facts(**changes):
    value = {"cancellation": False, "cancellation_reason": None, "deposit_reconciled": True, "deposit_settlement_identity": "a" * 64, "actual_start_date": "2026-08-01", "actual_end_date": None, "evaluation_at": "2026-08-01T00:00:00+00:00", "completion_instant": None, "completion_facts_consistent": True, "actual_start_reconfirmed": True, "effective_scheduling_generation_id": 1, "official_service_dates": ("2026-08-01",), "transition_blockers": {"enter_service": (), "auto_complete": ()}, "manual_correction_target": None}
    value.update(changes)
    return value


def test_validates_exact_canonical_lifecycle_facts_schema():
    result = validate_order_lifecycle_facts("訂單成立", "deposit_reconciled", _facts())
    assert result.validated_facts.evaluation_at.tzinfo is not None
    assert result.validated_facts.deposit_settlement_identity == "a" * 64


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
