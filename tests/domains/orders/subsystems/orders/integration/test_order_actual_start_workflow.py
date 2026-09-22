"""
File: test_order_actual_start_workflow.py
Description: 驗證實際開工 command 契約及非 AutoComplete workflow 的 lifecycle 邊界。
"""

from dataclasses import replace
from datetime import date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pymysql.err import IntegrityError

from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.errors import ErrorCategory
from shared_kernel.money import MoneyNTD
from domains.orders.lifecycle import (
    OrderLifecycleRootFacts,
    OrderLifecycleStatus,
    _alert_codes,
    _lifecycle_status,
)
from domains.orders.actual_start import (
    ActualStartBlocker,
    ActualStartCandidateError,
    ActualStartAssignmentFacts,
    ActualStartOrderFacts,
    ActualStartReconfirmationFacts,
    ActualStartReconfirmationState,
    ActualStartSchedulingFacts,
    build_actual_start_candidate,
)
from domains.orders.terms import OrderAggregateFacts, OrderTerms, ServiceTimeTerms
from domains.client_finance.obligation_planning import ClientFinanceTermsSourceFacts, ClientPaymentTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import AssignmentIdentityResolution, EffectiveAssignmentSegment, SchedulingGenerationFacts
from subsystems.payroll.terms_impact import CasePayrollPolicyTerms, PayrollTermsSourceFacts, SourceAssignmentPayrollTerms
from subsystems.orders.actual_start_workflow import ActualStartApplyRequest, ActualStartWorkflow, ActualStartWorkflowContext, ActualStartWorkflowError, _build_receipt, _effective_staff_payment_due_date, _persist_order_projection
from subsystems.orders.terms_workflow import CommandClaimState, OrderTermsReceipt, SchedulingReplacementResult, TermsWorkflowFacts
from infrastructure.mysql.order_actual_start_repository import (
    _is_effective_staff_date_conflict, _receipt_payload, _stored_receipt,
)
from api.dependencies.order_actual_start import ActualStartApplication
from subsystems.orders.actual_start_workflow import HistoricalActualStartSourceAssignment


def _request(*, reason: str = "confirm service start") -> ActualStartApplyRequest:
    return ActualStartApplyRequest(
        "CASE-1",
        date(2026, 8, 3),
        ExpectedVersion(1),
        ExpectedVersion(2),
        ExpectedVersion(3),
        ExpectedVersion(4),
        PreviewFingerprint("a" * 64),
        IdempotencyKey("actual-start-1"),
        ActorContext("admin"),
        reason,
        CorrelationId("actual-start-correlation"),
    )


def test_actual_start_request_uses_direct_canonical_source_contract() -> None:
    request = _request()

    assert request.case_no == "CASE-1"
    assert request.new_actual_start_date == date(2026, 8, 3)


def test_actual_start_request_rejects_blank_change_reason() -> None:
    with pytest.raises(ValueError, match="change reason"):
        _request(reason=" ")


def test_restarted_historical_actual_start_routes_directly_through_unique_pairing() -> None:
    shared_facts = SimpleNamespace(
        lifecycle=SimpleNamespace(historical_precision_restarted=True),
        scheduling=SimpleNamespace(segments=()),
    )

    class Repository:
        def load_for_preview(self, case_no):
            assert case_no == "CASE-1"
            return SimpleNamespace(shared_facts=shared_facts)

    planner_lock_modes = []

    class Planner:
        def calculate(self, case_no, actual_start_date, *, for_update):
            assert (case_no, actual_start_date) == ("CASE-1", date(2026, 8, 3))
            planner_lock_modes.append(("dates", for_update))
            return (date(2026, 8, 3), date(2026, 8, 4))

        def load_restart_source_assignments(self, case_no, *, for_update):
            assert case_no == "CASE-1"
            planner_lock_modes.append(("pairing", for_update))
            return (HistoricalActualStartSourceAssignment(None, 16),)

    calls = []

    class Workflow:
        def preview_historical_source(self, case_no, actual_start_date, **values):
            calls.append(("preview", case_no, actual_start_date, values))
            return "historical-preview"

        def apply_historical_source(self, request, **values):
            service_dates, assignments = values["source_loader"]()
            calls.append((
                "apply",
                request.case_no,
                request.new_actual_start_date,
                service_dates,
                assignments,
            ))
            return "historical-receipt"

        def preview(self, *_args, **_kwargs):
            raise AssertionError("generic preview must not handle a restarted historical tombstone")

        def apply(self, *_args, **_kwargs):
            raise AssertionError("generic apply must not handle a restarted historical tombstone")

    application = ActualStartApplication(Repository(), Workflow(), Planner())

    assert application.preview("CASE-1", date(2026, 8, 3)) == "historical-preview"
    assert application.apply(_request()) == "historical-receipt"
    assert planner_lock_modes == [
        ("dates", False),
        ("pairing", False),
        ("dates", True),
        ("pairing", True),
    ]
    assert calls == [
        (
            "preview", "CASE-1", date(2026, 8, 3),
            {
                "recalculated_service_dates": (date(2026, 8, 3), date(2026, 8, 4)),
                "source_staff_ids": (16,),
                "source_assignment_ids": (None,),
            },
        ),
        (
            "apply", "CASE-1", date(2026, 8, 3),
            (date(2026, 8, 3), date(2026, 8, 4)),
            (HistoricalActualStartSourceAssignment(None, 16),),
        ),
    ]


def test_actual_start_preserves_an_existing_staff_payment_due_date_across_months() -> None:
    assert _effective_staff_payment_due_date(
        date(2026, 8, 15),
        date(2026, 9, 15),
    ) == date(2026, 8, 15)


def test_actual_start_uses_the_calculated_due_date_only_when_none_exists() -> None:
    assert _effective_staff_payment_due_date(
        None,
        date(2026, 10, 15),
    ) == date(2026, 10, 15)


def test_full_subsidy_actual_start_uses_one_zero_client_and_42000_staff_plan() -> None:
    service_dates = tuple(date(2026, 8, day) for day in range(6, 21))
    segment = EffectiveAssignmentSegment(
        assignment_id=101,
        staff_id=11,
        sequence=1,
        service_day_count=15,
        assigned_start_date=service_dates[0],
        assigned_end_date=service_dates[-1],
        official_service_dates=service_dates,
    )
    facts = TermsWorkflowFacts(
        order=OrderAggregateFacts(
            "CASE-FULL-SUBSIDY",
            1,
            OrderTerms(
                service_dates[0],
                15,
                8,
                MoneyNTD(0),
                ServiceTimeTerms(None, None, None),
            ),
            False,
            "補助市民",
        ),
        scheduling=SchedulingGenerationFacts(
            "CASE-FULL-SUBSIDY", 2, 1, (segment,), False
        ),
        planned_service_dates=service_dates,
        planned_end_date=service_dates[-1],
        client_finance=ClientFinanceTermsSourceFacts(
            "CASE-FULL-SUBSIDY",
            3,
            ClientPaymentTerms(
                0,
                MoneyNTD(350),
                date(2026, 8, 1),
                date(2026, 8, 15),
                None,
            ),
            (),
            (),
            identity_status="補助市民",
        ),
        payroll=PayrollTermsSourceFacts(
            "CASE-FULL-SUBSIDY",
            4,
            (
                SourceAssignmentPayrollTerms(
                    101,
                    11,
                    "payroll-rate:subsidized-citizen:v1",
                    PayrollPolicyKind.SUBSIDIZED_CITIZEN,
                ),
            ),
            (),
            None,
            CasePayrollPolicyTerms(
                "payroll-rate:subsidized-citizen:v1",
                PayrollPolicyKind.SUBSIDIZED_CITIZEN,
            ),
        ),
        lifecycle=OrderLifecycleRootFacts(
            "CASE-FULL-SUBSIDY",
            OrderLifecycleStatus.ESTABLISHED,
            True,
            None,
            False,
            False,
            False,
        ),
    )

    class _PreviewRepository:
        def __init__(self, shared_facts):
            self.shared_facts = shared_facts

        def load_for_preview(self, case_no):
            assert case_no == "CASE-FULL-SUBSIDY"
            return ActualStartWorkflowContext(
                self.shared_facts,
                ActualStartReconfirmationFacts(
                    ActualStartReconfirmationState.NOT_REQUIRED,
                    None,
                    None,
                    False,
                ),
            )

    preview = ActualStartWorkflow(
        _PreviewRepository(facts),
        lambda: None,
        FixedBusinessClock(datetime(2026, 8, 6, 9, tzinfo=TAIPEI_TIME_ZONE)),
    ).preview(
        "CASE-FULL-SUBSIDY",
        service_dates[0],
        recalculated_service_dates=service_dates,
    )

    assert sum(plan.amount.amount for plan in preview.client_finance_impact.stage_plans) == 0
    assert sum(action.amount.amount for action in preview.payroll_impact.actions) == 42_000
    assert {action.due_date for action in preview.payroll_impact.actions} == {date(2026, 10, 15)}
    assert preview.staff_payment_due_date == date(2026, 10, 15)

    preserved_facts = replace(
        facts,
        payroll=replace(facts.payroll, staff_payment_due_date=date(2026, 8, 15)),
    )
    preserved_preview = ActualStartWorkflow(
        _PreviewRepository(preserved_facts),
        lambda: None,
        FixedBusinessClock(datetime(2026, 8, 6, 9, tzinfo=TAIPEI_TIME_ZONE)),
    ).preview(
        "CASE-FULL-SUBSIDY",
        service_dates[0],
        recalculated_service_dates=service_dates,
    )
    assert {action.due_date for action in preserved_preview.payroll_impact.actions} == {date(2026, 8, 15)}

    class _PersistenceCapture:
        command = None

        def update_actual_start(self, command):
            self.command = command

    capture = _PersistenceCapture()
    _persist_order_projection(
        capture,
        SimpleNamespace(case_no="CASE-FULL-SUBSIDY", new_actual_start_date=service_dates[0]),
        preserved_preview,
        _build_receipt(preserved_preview),
    )
    assert capture.command.staff_payment_due_date == date(2026, 8, 15)


def test_actual_start_lifecycle_impact_cannot_bypass_auto_completion_owner() -> None:
    roots = OrderLifecycleRootFacts(
        case_no="CASE-1",
        current_status=OrderLifecycleStatus.ESTABLISHED,
        contract_completed=True,
        actual_start_date=date(2026, 8, 20),
        actual_start_reconfirmed=True,
        cancellation_effective=False,
        service_data_locked=False,
    )
    settlement = SimpleNamespace(deposit_settled=True)

    status = _lifecycle_status(
        roots,
        settlement,
        completion_reached=False,
        evaluation_at=datetime(2026, 8, 24, 18, 0, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    assert status is OrderLifecycleStatus.IN_SERVICE


def test_restarted_historical_actual_start_enters_service_without_deposit_or_contract() -> None:
    roots = OrderLifecycleRootFacts(
        case_no="CASE-HISTORICAL-RESTART",
        current_status=OrderLifecycleStatus.ESTABLISHED,
        contract_completed=False,
        actual_start_date=date(2026, 8, 20),
        actual_start_reconfirmed=True,
        cancellation_effective=False,
        service_data_locked=False,
        historical_precision_restarted=True,
    )

    settlement = SimpleNamespace(deposit_settled=False)
    evaluation_at = datetime(2026, 8, 20, 9, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    status = _lifecycle_status(
        roots,
        settlement,
        completion_reached=False,
        evaluation_at=evaluation_at,
    )

    assert status is OrderLifecycleStatus.IN_SERVICE
    assert _alert_codes(roots, settlement, evaluation_at) == ()


@pytest.mark.parametrize("actual_start_date", [None, date(2026, 8, 21)])
def test_restarted_historical_unstarted_or_future_actual_start_stays_established(
    actual_start_date,
) -> None:
    roots = OrderLifecycleRootFacts(
        case_no="CASE-HISTORICAL-FUTURE",
        current_status=OrderLifecycleStatus.ESTABLISHED,
        contract_completed=False,
        actual_start_date=actual_start_date,
        actual_start_reconfirmed=actual_start_date is not None,
        cancellation_effective=False,
        service_data_locked=False,
        historical_precision_restarted=True,
    )

    status = _lifecycle_status(
        roots,
        SimpleNamespace(deposit_settled=False),
        completion_reached=False,
        evaluation_at=datetime(2026, 8, 20, 9, 0, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    assert status is OrderLifecycleStatus.ESTABLISHED


def test_actual_start_maps_effective_staff_date_duplicate_to_typed_conflict() -> None:
    error = IntegrityError(
        1062,
        "Duplicate entry '531-2026-08-20-1' for key "
        "'staff_schedule.uq_staff_schedule_effective_date'",
    )

    assert _is_effective_staff_date_conflict(error) is True
    assert _is_effective_staff_date_conflict(
        IntegrityError(
            1062,
            "Duplicate entry '531-2026-08-11' for key "
            "'scheduling_effective_occupancy.PRIMARY'",
        )
    ) is True
    assert _is_effective_staff_date_conflict(IntegrityError(1062, "other")) is False


def test_actual_start_can_replace_legacy_dates_with_recalculated_official_dates() -> None:
    order = ActualStartOrderFacts(
        "CASE-1",
        3,
        None,
        False,
        ServiceTimeTerms(None, None, None),
    )
    scheduling = ActualStartSchedulingFacts(
        "CASE-1",
        5,
        1,
        date(2026, 8, 1),
        (
            ActualStartAssignmentFacts(
                11,
                22,
                1,
                date(2026, 8, 1),
                date(2026, 8, 3),
                (date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)),
            ),
        ),
    )

    candidate = build_actual_start_candidate(
        order,
        scheduling,
        date(2026, 8, 8),
        8,
        (date(2026, 8, 8), date(2026, 8, 11), date(2026, 8, 12)),
    )

    assert candidate.official_service_dates == (
        date(2026, 8, 8),
        date(2026, 8, 11),
        date(2026, 8, 12),
    )
    assert candidate.actual_end_date == date(2026, 8, 12)


def test_actual_start_keeps_current_service_data_lock_blocker() -> None:
    order = ActualStartOrderFacts(
        "CASE-LOCKED", 3, None, True, ServiceTimeTerms(None, None, None)
    )
    scheduling = ActualStartSchedulingFacts(
        "CASE-LOCKED",
        5,
        1,
        date(2026, 8, 1),
        (
            ActualStartAssignmentFacts(
                11, 22, 1, date(2026, 8, 1), date(2026, 8, 1),
                (date(2026, 8, 1),),
            ),
        ),
    )

    with pytest.raises(ActualStartCandidateError) as error:
        build_actual_start_candidate(order, scheduling, date(2026, 8, 2), 8)

    assert error.value.blocker is ActualStartBlocker.SERVICE_DATA_LOCKED


def test_normal_actual_start_still_requires_canonical_scheduling_assignment() -> None:
    order = ActualStartOrderFacts(
        "CASE-NORMAL", 3, None, False, ServiceTimeTerms(None, None, None)
    )
    scheduling = ActualStartSchedulingFacts(
        "CASE-NORMAL", 5, 1, date(2026, 8, 1), ()
    )

    with pytest.raises(ActualStartCandidateError) as error:
        build_actual_start_candidate(order, scheduling, date(2026, 8, 2), 8)

    assert error.value.blocker is ActualStartBlocker.SCHEDULING_ASSIGNMENTS_REQUIRED
