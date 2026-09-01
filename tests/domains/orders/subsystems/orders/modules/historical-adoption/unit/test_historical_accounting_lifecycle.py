from domains.orders.lifecycle import (
    OrderLifecycleStatus,
    project_historical_accounting_completion_status,
)


def test_only_bilateral_real_settlement_completes_historical_accounting() -> None:
    assert project_historical_accounting_completion_status(
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        client_settled=True,
        all_staff_settled=True,
        service_day_counts_complete=True,
    ) is OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED


def test_any_open_owner_keeps_historical_service_completed() -> None:
    assert project_historical_accounting_completion_status(
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        client_settled=True,
        all_staff_settled=False,
        service_day_counts_complete=True,
    ) is OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED
