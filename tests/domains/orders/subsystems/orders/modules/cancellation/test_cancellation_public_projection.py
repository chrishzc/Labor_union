"""Cancellation keeps payroll execution-only context out of its public preview."""
from types import SimpleNamespace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from api.routes.order_cancellation import _payroll_impact_payload
from api.schemas.order_cancellation import CancellationPayrollImpactView
from api.routes.order_cancellation import _current_service_days
from domains.orders.cancellation import (
    CancellationAssignmentFacts, CancellationCandidateError, CancellationOrderFacts,
    CancellationSchedulingFacts, ConfirmedServiceDay, build_cancellation_candidate,
)
from shared_kernel.clock import FixedBusinessClock


def test_payroll_execution_context_does_not_break_strict_cancellation_client():
    public = dict(case_no="CASE-1", expected_payroll_version=1, resulting_payroll_version=2,
                  payroll={"assignments": [], "floor_fee_total": {"amount": 0}},
                  carried_rate_snapshots=[], actions=[], special_pay_events=[], blockers=[], fingerprint="a" * 64)
    impact = SimpleNamespace(**public, frozen_settlements=(object(),), rate_source_assignments=(object(),))
    result = _payroll_impact_payload(impact)
    assert result == public
    assert CancellationPayrollImpactView.model_validate(result).model_dump() == public
    assert _payroll_impact_payload(None) is None


def test_cancellation_payroll_hours_are_json_numbers_for_the_strict_ui():
    public = dict(case_no='CASE-1', expected_payroll_version=1, resulting_payroll_version=2,
                  payroll={'assignments': [{'actual_hours': Decimal('28.5'), 'double_pay_hours': Decimal('0')}]},
                  carried_rate_snapshots=[], actions=[], special_pay_events=[], blockers=[], fingerprint='a' * 64)
    payload = _payroll_impact_payload(SimpleNamespace(**public))
    assert payload['payroll']['assignments'][0] == {'actual_hours': 28.5, 'double_pay_hours': 0}


def test_cancellation_query_excludes_future_days_using_the_taipei_business_date():
    clock = FixedBusinessClock(datetime(2026, 10, 24, 16, 30, tzinfo=timezone.utc))
    scheduling = CancellationSchedulingFacts('CASE-1', 1, 1, (
        CancellationAssignmentFacts(1, 8, 1, (date(2026, 10, 24), date(2026, 10, 25))),
        CancellationAssignmentFacts(2, 9, 2, (date(2026, 10, 26),)),
    ))
    assert _current_service_days(scheduling, clock.today()) == [
        {'service_date': date(2026, 10, 24), 'staff_id': 8, 'reason': None},
        {'service_date': date(2026, 10, 25), 'staff_id': 8, 'reason': None},
    ]


def test_scheduled_start_can_be_cancelled_with_confirmed_zero_actual_service():
    today = date(2026, 10, 25)
    order = CancellationOrderFacts('CASE-1', 1, 3, 8, today, True, False)
    scheduling = CancellationSchedulingFacts('CASE-1', 1, 1, (
        CancellationAssignmentFacts(1, 8, 1, (today, date(2026, 10, 26))),
    ))
    result = build_cancellation_candidate(order, scheduling, today, ())
    assert result.official_service_day_count == 0
    assert result.official_service_hours == 0
    assert result.scheduling.assignments == ()
    assert result.scheduling.cancelled_assignment_ids == (1,)
    assert result.scheduling.buffers == ()
    with pytest.raises(CancellationCandidateError, match='service_date_in_future'):
        build_cancellation_candidate(order, scheduling, today, (
            ConfirmedServiceDay(date(2026, 10, 26), 8),
        ))


def test_cancellation_still_rejects_reducing_locked_full_service():
    order = CancellationOrderFacts('CASE-1', 1, 3, 8, date(2026, 10, 22), True, True)
    scheduling = CancellationSchedulingFacts('CASE-1', 1, 1, ())
    with pytest.raises(CancellationCandidateError, match='service_data_locked'):
        build_cancellation_candidate(order, scheduling, date(2026, 10, 25), ())
