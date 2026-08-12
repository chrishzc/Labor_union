from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from domains.orders.lifecycle import (
    OrderLifecycleStatus,
    _lifecycle_status,
)


def _facts(*, contract_completed: bool, actual_start_date: date | None):
    return SimpleNamespace(
        current_status=OrderLifecycleStatus.DISCUSSION,
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
