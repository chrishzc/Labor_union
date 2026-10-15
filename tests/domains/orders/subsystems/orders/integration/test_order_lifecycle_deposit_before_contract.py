"""
File: tests/test_order_lifecycle_deposit_before_contract.py
Description: 驗證訂金與契約條件的生命週期轉換，待補件不得自動前進。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from domains.orders.lifecycle import (
    OrderLifecycleStatus,
    _lifecycle_status,
)


def _facts(
    *,
    contract_completed: bool,
    actual_start_date: date | None,
    current_status=OrderLifecycleStatus.DISCUSSION,
    deposit_gate_override_active=False,
):
    return SimpleNamespace(
        current_status=current_status,
        cancellation_effective=False,
        actual_start_date=actual_start_date,
        actual_start_reconfirmed=True,
        contract_completed=contract_completed,
        historical_precision_restarted=False,
        deposit_gate_override_active=deposit_gate_override_active,
    )


def _settlement():
    return SimpleNamespace(deposit_settled=True)


def test_deposit_can_establish_order_before_customer_contract_is_completed():
    status = _lifecycle_status(
        _facts(contract_completed=False, actual_start_date=None),
        _settlement(),
        completion_reached=False,
        evaluation_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )

    assert status is OrderLifecycleStatus.ESTABLISHED


def test_uncompleted_customer_contract_blocks_entering_service_after_deposit():
    status = _lifecycle_status(
        _facts(contract_completed=False, actual_start_date=date(2026, 8, 9)),
        _settlement(),
        completion_reached=False,
        evaluation_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )

    assert status is OrderLifecycleStatus.ESTABLISHED


def test_completed_customer_contract_allows_normal_enter_service_rule():
    status = _lifecycle_status(
        _facts(contract_completed=True, actual_start_date=date(2026, 8, 9)),
        _settlement(),
        completion_reached=False,
        evaluation_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )

    assert status is OrderLifecycleStatus.IN_SERVICE


def test_pending_completion_order_never_advances_from_lifecycle_evaluation():
    status = _lifecycle_status(
        _facts(
            contract_completed=True,
            actual_start_date=date(2026, 8, 9),
            current_status=OrderLifecycleStatus.PENDING_COMPLETION,
        ),
        _settlement(),
        completion_reached=False,
        evaluation_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )

    assert status is OrderLifecycleStatus.PENDING_COMPLETION


def test_unpaid_override_preserves_established_order_before_service():
    settlement = SimpleNamespace(deposit_settled=False)
    status = _lifecycle_status(
        _facts(contract_completed=True, actual_start_date=date(2026, 11, 15),
               deposit_gate_override_active=True),
        settlement, False, datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    assert status is OrderLifecycleStatus.ESTABLISHED
    assert settlement.deposit_settled is False


def test_unpaid_override_allows_signed_reconfirmed_order_to_enter_service():
    from domains.orders.lifecycle import _alert_codes
    settlement = SimpleNamespace(deposit_settled=False)
    roots = _facts(contract_completed=True, actual_start_date=date(2026, 9, 14),
                   deposit_gate_override_active=True)
    now = datetime(2026, 10, 15, tzinfo=timezone.utc)
    assert _lifecycle_status(roots, settlement, False, now) is OrderLifecycleStatus.IN_SERVICE
    assert _alert_codes(roots, settlement, now) == ()
    assert settlement.deposit_settled is False


def test_expired_override_still_blocks_unpaid_order():
    from domains.orders.lifecycle import _alert_codes
    roots = _facts(contract_completed=True, actual_start_date=date(2026, 9, 14))
    settlement = SimpleNamespace(deposit_settled=False)
    now = datetime(2026, 10, 15, tzinfo=timezone.utc)
    assert _lifecycle_status(roots, settlement, False, now) is OrderLifecycleStatus.DISCUSSION
    assert _alert_codes(roots, settlement, now) == ('enter_service.deposit_required_before_service',)
