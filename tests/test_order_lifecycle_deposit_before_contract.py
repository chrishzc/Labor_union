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
):
    return SimpleNamespace(
        current_status=current_status,
        cancellation_effective=False,
        actual_start_date=actual_start_date,
        actual_start_reconfirmed=True,
        contract_completed=contract_completed,
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
