"""
File: test_historical_completion_projector.py
Description: 驗證 HOB-E fresh projector 只依 owner roots 同步 Step 11 與歷史警示。
"""

from datetime import date

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.historical_completion_oracle import (
    CompletionOwner,
    HistoricalCompletionFacts,
    HistoricalOrdersCompletionReadback,
    HistoricalSettlementReadback,
    HistoricalSettlementSourceVersion,
    SettlementSourceKind,
    evaluate_historical_completion,
)
from subsystems.orders.historical_completion_projector import (
    project_historical_completion,
)


def _staff_sources():
    return tuple(sorted(
        HistoricalSettlementSourceVersion(kind, f"source:{index}", 1)
        for index, kind in enumerate(
            (
                SettlementSourceKind.PAYROLL_CASE_ACCOUNT,
                SettlementSourceKind.STAFF_OBLIGATION,
                SettlementSourceKind.STAFF_OBLIGATION_EVENT,
                SettlementSourceKind.STAFF_PAYABLE_ACCOUNT,
                SettlementSourceKind.STAFF_PAYABLE_PROJECTION,
                SettlementSourceKind.STAFF_PAYOUT_EVENT,
                SettlementSourceKind.STAFF_PAYOUT_ALLOCATION,
                SettlementSourceKind.STAFF_BANK_FACT,
            )
        )
    ))


def _result(*, client_open: int = 0, staff_available: bool = True):
    facts = HistoricalCompletionFacts(
        "CASE-1",
        HistoricalOrdersCompletionReadback(
            "CASE-1",
            3,
            OrderLifecycleStatus.COMPLETED,
            "completion:1",
            date(2026, 1, 1),
            "service-facts:1",
            (date(2026, 1, 1),),
            1,
            True,
        ),
        HistoricalSettlementReadback(
            "CASE-1",
            CompletionOwner.CLIENT_FINANCE,
            4,
            "client-settlement:1",
            1,
            client_open,
            "client-allocation:1",
        ),
        HistoricalSettlementReadback(
            "CASE-1",
            CompletionOwner.STAFF_PAYABLES,
            None,
            "staff-settlement:1",
            1,
            0,
            "staff-allocation:1",
            _staff_sources(),
            staff_available,
        ),
    )
    return evaluate_historical_completion(facts)


def test_all_owner_roots_close_step_11_and_historical_alerts_together() -> None:
    projection = project_historical_completion(_result())

    assert projection.step_11_completed
    assert projection.historical_alerts_completed
    assert projection.active_alerts == ()
    assert projection.source_fingerprint != projection.projection_fingerprint


def test_missing_owner_root_stays_actionable_and_blocks_both_terminal_views() -> None:
    projection = project_historical_completion(_result(client_open=1))

    assert not projection.step_11_completed
    assert not projection.historical_alerts_completed
    alert = next(
        item for item in projection.active_alerts
        if item.code == "client_finance_settlement_open"
    )
    assert alert.owner is CompletionOwner.CLIENT_FINANCE
    assert alert.referral.value == "client_finance.settlement"


def test_unavailable_owner_never_projects_false_completion() -> None:
    projection = project_historical_completion(_result(staff_available=False))

    assert projection.state.value == "unavailable"
    assert projection.step_11_status == "unavailable"
    assert not projection.step_11_completed


def test_historical_count_path_does_not_require_fabricated_service_dates() -> None:
    facts = HistoricalCompletionFacts(
        "CASE-1",
        HistoricalOrdersCompletionReadback(
            "CASE-1",
            3,
            OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
            "historical-adoption:1",
            date(2026, 1, 1),
            None,
            (),
            40,
            False,
            historical_service_day_count_identity="historical-days:1",
            historical_assignment_day_counts=(("assignment:1", 7, 3),),
        ),
        HistoricalSettlementReadback(
            "CASE-1", CompletionOwner.CLIENT_FINANCE, 4,
            "client-settlement:1", 1, 0, "client-allocation:1",
        ),
        HistoricalSettlementReadback(
            "CASE-1", CompletionOwner.STAFF_PAYABLES, None,
            "staff-settlement:1", 1, 0, "staff-allocation:1", _staff_sources(),
        ),
    )

    projection = project_historical_completion(evaluate_historical_completion(facts))

    assert projection.step_11_completed
    assert not any(
        item.code.startswith("scheduling_service") for item in projection.active_alerts
    )


def test_historical_count_path_stays_blocked_until_days_are_confirmed() -> None:
    facts = HistoricalCompletionFacts(
        "CASE-1",
        HistoricalOrdersCompletionReadback(
            "CASE-1", 3, OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
            "historical-adoption:1", date(2026, 1, 1), None, (), 40, False,
        ),
        HistoricalSettlementReadback(
            "CASE-1", CompletionOwner.CLIENT_FINANCE, 4,
            "client-settlement:1", 1, 0, "client-allocation:1",
        ),
        HistoricalSettlementReadback(
            "CASE-1", CompletionOwner.STAFF_PAYABLES, None,
            "staff-settlement:1", 1, 0, "staff-allocation:1", _staff_sources(),
        ),
    )

    projection = project_historical_completion(evaluate_historical_completion(facts))

    assert not projection.step_11_completed
    assert {item.code for item in projection.active_alerts} >= {
        "historical_actual_service_days_required",
        "historical_actual_service_days_assignment_mismatch",
    }
