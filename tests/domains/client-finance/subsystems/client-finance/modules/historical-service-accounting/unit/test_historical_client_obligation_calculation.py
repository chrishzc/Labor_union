"""Historical Client Finance uses count facts and never payment-stage dates."""

from domains.client_finance.historical_obligation_calculation import (
    build_historical_client_obligation_candidate,
)
from shared_kernel.money import MoneyNTD


def test_three_actual_days_replace_forty_contract_days_for_general_citizen() -> None:
    candidate = build_historical_client_obligation_candidate(
        identity_status="一般市民",
        client_policy_version="client-policy:case-19",
        client_hourly_rate=MoneyNTD(275),
        actual_service_days=3,
        service_hours_per_day=9,
        historical_floor_fee=MoneyNTD(300),
    )

    assert candidate.actual_service_hours == 27
    assert candidate.service_receivable == MoneyNTD(7_425)
    assert candidate.total_receivable == MoneyNTD(7_725)


def test_subsidized_client_only_owes_hours_beyond_subsidy_plus_floor_fee() -> None:
    candidate = build_historical_client_obligation_candidate(
        identity_status="補助市民",
        client_policy_version="client-policy:subsidized",
        client_hourly_rate=MoneyNTD(350),
        actual_service_days=15,
        service_hours_per_day=9,
        historical_floor_fee=MoneyNTD(1_500),
    )

    assert candidate.subsidy_hours == 120
    assert candidate.self_pay_service_hours == 15
    assert candidate.total_receivable == MoneyNTD(6_750)


def test_non_citizen_uses_non_citizen_client_rate() -> None:
    candidate = build_historical_client_obligation_candidate(
        identity_status="非市民",
        client_policy_version="client-policy:non-citizen",
        client_hourly_rate=MoneyNTD(365),
        actual_service_days=2,
        service_hours_per_day=9,
        historical_floor_fee=MoneyNTD(0),
    )

    assert candidate.total_receivable == MoneyNTD(6_570)
