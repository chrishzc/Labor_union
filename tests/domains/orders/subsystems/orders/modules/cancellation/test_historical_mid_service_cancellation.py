from datetime import date
from types import SimpleNamespace

import pytest

from domains.orders.cancellation import CancellationOrderFacts, ConfirmedServiceDay
from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.identities import CorrelationId
from subsystems.orders.cancellation_workflow import (
    CancellationWorkflowError,
    _effective_order_facts,
    _ensure_cancellation_allowed,
)


def _facts(*, historical_origin: bool, status=OrderLifecycleStatus.CANCELLED):
    return SimpleNamespace(
        order=CancellationOrderFacts(
            "HIST-1",
            3,
            30,
            8,
            None,
            False,
            False,
        ),
        lifecycle=SimpleNamespace(
            current_status=status,
            cancellation_effective=status is OrderLifecycleStatus.CANCELLED,
        ),
        historical_cancellation_origin=historical_origin,
    )


def _confirmed_days():
    return (
        ConfirmedServiceDay(date(2026, 8, 3), 9, "historical service confirmation"),
        ConfirmedServiceDay(date(2026, 8, 1), 9, "historical service confirmation"),
    )


def test_historical_cancelled_case_derives_actual_start_from_confirmed_daily_facts():
    effective = _effective_order_facts(_facts(historical_origin=True), _confirmed_days())

    assert effective.actual_start_date == date(2026, 8, 1)
    assert effective.service_started is True


def test_normal_or_non_cancelled_case_does_not_receive_historical_exception():
    normal = _effective_order_facts(_facts(historical_origin=False), _confirmed_days())
    wrong_status = _effective_order_facts(
        _facts(
            historical_origin=True,
            status=OrderLifecycleStatus.ESTABLISHED,
        ),
        _confirmed_days(),
    )

    assert normal.actual_start_date is None
    assert normal.service_started is False
    assert wrong_status.actual_start_date is None
    assert wrong_status.service_started is False


def test_historical_cancelled_case_with_confirmed_days_can_enter_recovery():
    _ensure_cancellation_allowed(
        _facts(historical_origin=True),
        _confirmed_days(),
        CorrelationId("historical-recovery"),
    )


def test_historical_cancelled_case_without_confirmed_days_remains_closed():
    with pytest.raises(CancellationWorkflowError):
        _ensure_cancellation_allowed(
            _facts(historical_origin=True),
            (),
            CorrelationId("historical-recovery-without-days"),
        )


@pytest.mark.parametrize("lock", [False, True])
def test_cancellation_reader_carries_financial_identity_from_payroll_baseline(monkeypatch, lock):
    from infrastructure.mysql.order_cancellation_read_model import _with_financial_assignment_identities
    from infrastructure.mysql import service_date_adjustment_repository as baseline
    from subsystems.payroll.terms_impact import SourceAssignmentPayrollTerms
    from domains.payroll.calculation import PayrollPolicyKind

    def load(cursor, generation, assignments, service_days, *, lock):
        assert (cursor, generation, assignments, service_days) == ("cursor", 3, ({"id": 30},), 2)
        assert lock is expected_lock
        return ({"assignment_id": 30, "financial_assignment_identity": "assignment:2"},)

    expected_lock = lock
    monkeypatch.setattr(baseline, "load_payroll_service_dates", load)
    source = SimpleNamespace(source_terms=(SourceAssignmentPayrollTerms(30, 2, "v1", PayrollPolicyKind.CITIZEN),))
    from subsystems.payroll.terms_impact import PayrollTermsSourceFacts
    payroll = PayrollTermsSourceFacts("CASE-1", 1, source.source_terms, (), None)
    result = _with_financial_assignment_identities("cursor", payroll, 3, ({"id": 30},), 2, lock=lock)
    assert result.source_terms[0].source_assignment_id == 30
    assert result.source_terms[0].financial_assignment_identity == "assignment:2"
