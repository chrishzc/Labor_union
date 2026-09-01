from decimal import Decimal

import pytest

from domains.orders.historical_service_accounting import (
    HistoricalActualServiceDaysInput,
    HistoricalServiceAssignmentFacts,
    build_historical_actual_service_days_candidate,
)


def test_historical_three_days_ignores_forty_day_contract_and_double_pay():
    candidate = build_historical_actual_service_days_candidate(
        case_no="115000019",
        assignments=(HistoricalServiceAssignmentFacts("assignment-019", 3),),
        inputs=(HistoricalActualServiceDaysInput("assignment-019", 3, 3),),
        contracted_service_days=40,
        service_hours_per_day=Decimal("24"),
        contractual_floor_fee_ntd=4000,
    )

    assert candidate.total_actual_service_days == 3
    assert candidate.total_actual_service_hours == Decimal("72")
    assert candidate.historical_floor_fee_ntd == 300
    assert candidate.historical_double_pay_days == 0
    assert candidate.historical_double_pay_hours == 0
    assert candidate.allocations[0].floor_fee_ntd == 300


def test_historical_days_may_exceed_contract_and_floor_fee_keeps_scaling():
    candidate = build_historical_actual_service_days_candidate(
        case_no="CASE-26",
        assignments=(
            HistoricalServiceAssignmentFacts("assignment-a", 3),
            HistoricalServiceAssignmentFacts("assignment-b", 7),
        ),
        inputs=(
            HistoricalActualServiceDaysInput("assignment-a", 3, 15),
            HistoricalActualServiceDaysInput("assignment-b", 7, 11),
        ),
        contracted_service_days=25,
        service_hours_per_day=Decimal("24"),
        contractual_floor_fee_ntd=1000,
    )

    assert candidate.total_actual_service_days == 26
    assert candidate.historical_floor_fee_ntd == 1040
    assert tuple(item.floor_fee_ntd for item in candidate.allocations) == (600, 440)
    assert sum(item.floor_fee_ntd for item in candidate.allocations) == 1040


@pytest.mark.parametrize("days", (0, -1, True, Decimal("1.5")))
def test_historical_days_must_be_positive_integers(days):
    with pytest.raises(ValueError, match="historical_actual_service_days_invalid"):
        build_historical_actual_service_days_candidate(
            case_no="CASE-1",
            assignments=(HistoricalServiceAssignmentFacts("assignment-a", 3),),
            inputs=(HistoricalActualServiceDaysInput("assignment-a", 3, days),),
            contracted_service_days=25,
            service_hours_per_day=Decimal("24"),
            contractual_floor_fee_ntd=1000,
        )


@pytest.mark.parametrize(
    "inputs",
    (
        (HistoricalActualServiceDaysInput("assignment-a", 3, 1),),
        (
            HistoricalActualServiceDaysInput("assignment-a", 3, 1),
            HistoricalActualServiceDaysInput("assignment-a", 3, 1),
        ),
        (
            HistoricalActualServiceDaysInput("assignment-a", 3, 1),
            HistoricalActualServiceDaysInput("assignment-b", 99, 1),
        ),
    ),
)
def test_every_historical_assignment_requires_exactly_one_matching_staff_count(inputs):
    with pytest.raises(
        ValueError,
        match="historical_actual_service_days_assignment_mismatch",
    ):
        build_historical_actual_service_days_candidate(
            case_no="CASE-1",
            assignments=(
                HistoricalServiceAssignmentFacts("assignment-a", 3),
                HistoricalServiceAssignmentFacts("assignment-b", 7),
            ),
            inputs=inputs,
            contracted_service_days=25,
            service_hours_per_day=Decimal("24"),
            contractual_floor_fee_ntd=1000,
        )
