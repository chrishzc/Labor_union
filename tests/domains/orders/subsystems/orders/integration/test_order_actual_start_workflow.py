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
from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.scheduling.generation import AssignmentIdentityResolution
from subsystems.orders.actual_start_workflow import (
    ActualStartApplyRequest,
    ActualStartDateOnlyApplyRequest,
    ActualStartQueryFacts,
    ActualStartWorkflow,
    ActualStartWorkflowContext,
    ActualStartWorkflowError,
)
from subsystems.orders.terms_workflow import CommandClaimState, OrderTermsReceipt, SchedulingReplacementResult, TermsWorkflowFacts
from infrastructure.mysql.order_actual_start_repository import (
    MySqlOrderActualStartRepository,
    _is_effective_staff_date_conflict,
    _receipt_payload,
    _stored_receipt,
)
from infrastructure.mysql.order_terms_read_model import _service_started
from api.dependencies.order_actual_start import ActualStartApplication
from subsystems.orders.actual_start_workflow import HistoricalActualStartSourceAssignment


def _request(*, reason: str = "confirm service start") -> ActualStartApplyRequest:
    return ActualStartApplyRequest(
        "CASE-1",
        date(2026, 8, 3),
        ExpectedVersion(1),
        ExpectedVersion(2),
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
    query = ActualStartQueryFacts(
        "CASE-1", None, date(2026, 8, 1), False, 1,
        2, None, 3, 4, False, True,
    )

    class Repository:
        def load_actual_start_query(self, case_no, *, for_update):
            assert case_no == "CASE-1"
            assert for_update is False
            return query

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


def test_application_routes_unassigned_order_to_date_only_without_downstream_facts() -> None:
    query = ActualStartQueryFacts(
        "CASE-DATE", None, date(2026, 9, 1), False, 7,
        None, None, None, None, False, False,
    )

    class Repository:
        def load_actual_start_query(self, case_no, *, for_update):
            assert (case_no, for_update) == ("CASE-DATE", False)
            return query

        def load_for_preview(self, _case_no):
            raise AssertionError("date-only preview must not load downstream facts")

    class Workflow:
        def preview_date_only(self, facts, new_date):
            assert facts is query
            assert new_date == date(2026, 9, 2)
            return "date-only-preview"

        def preview(self, *_args):
            raise AssertionError("date-only preview must not enter rescheduling")

    application = ActualStartApplication(Repository(), Workflow())

    assert application.query("CASE-DATE") is query
    assert application.preview("CASE-DATE", date(2026, 9, 2)) == "date-only-preview"


def test_date_only_apply_updates_only_orders_root_and_returns_fresh_version() -> None:
    query = ActualStartQueryFacts(
        "CASE-DATE", None, date(2026, 9, 1), False, 7,
        None, None, None, None, False, False,
    )
    class UnitOfWork:
        committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            self.committed = True

    class Repository:
        saved = []

        def load_actual_start_query(self, case_no, *, for_update):
            assert (case_no, for_update) == ("CASE-DATE", True)
            return query

        def save_actual_start_date_only(self, command):
            self.saved.append(command)

    repository = Repository()
    unit_of_work = UnitOfWork()
    workflow = ActualStartWorkflow(
        repository,
        lambda: unit_of_work,
        FixedBusinessClock(datetime(2026, 9, 1, tzinfo=TAIPEI_TIME_ZONE)),
    )
    preview = workflow.preview_date_only(query, date(2026, 9, 2))
    request = ActualStartDateOnlyApplyRequest(
        "CASE-DATE",
        date(2026, 9, 2),
        ExpectedVersion(7),
        preview.fingerprint,
        CorrelationId("date-only-apply"),
    )

    result = workflow.apply_date_only(request)

    assert result.actual_start_date == date(2026, 9, 2)
    assert result.order_version == 8
    assert result.changed is True
    assert result.preview_fingerprint == preview.fingerprint
    assert repository.saved[0].expected_order_version == 7
    assert repository.saved[0].resulting_order_version == 8
    assert unit_of_work.committed is True


def test_date_only_apply_reports_typed_conflict_when_formal_assignment_appears() -> None:
    preview_facts = ActualStartQueryFacts(
        "CASE-DATE", None, date(2026, 9, 1), False, 7,
        None, None, None, None, False, False,
    )

    class UnitOfWork:
        committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            self.committed = True

    class Repository:
        saved = []

        def load_actual_start_query(self, case_no, *, for_update):
            assert (case_no, for_update) == ("CASE-DATE", True)
            return replace(preview_facts, has_formal_assignments=True)

        def save_actual_start_date_only(self, command):
            self.saved.append(command)

    repository = Repository()
    unit_of_work = UnitOfWork()
    workflow = ActualStartWorkflow(
        repository,
        lambda: unit_of_work,
        FixedBusinessClock(datetime(2026, 9, 1, tzinfo=TAIPEI_TIME_ZONE)),
    )
    preview = workflow.preview_date_only(preview_facts, date(2026, 9, 2))

    with pytest.raises(ActualStartWorkflowError) as exc_info:
        workflow.apply_date_only(ActualStartDateOnlyApplyRequest(
            "CASE-DATE",
            date(2026, 9, 2),
            ExpectedVersion(7),
            preview.fingerprint,
            CorrelationId("date-only-mode-conflict"),
        ))

    assert exc_info.value.error.category is ErrorCategory.CONFLICT
    assert exc_info.value.error.code == "actual_start_mode_changed"
    assert repository.saved == []
    assert unit_of_work.committed is False


def test_mysql_query_allows_missing_scheduling_finance_and_payroll_roots() -> None:
    class Cursor:
        row = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _params):
            normalized = " ".join(statement.lower().split())
            if "from orders o where o.case_no" in normalized:
                self.row = {
                    "case_no": "CASE-DATE",
                    "actual_start_date": None,
                    "start_date": date(2026, 9, 1),
                    "lifecycle_version": 7,
                    "service_data_locked": 0,
                }
            else:
                self.row = None

        def fetchone(self):
            return self.row

        def fetchall(self):
            return ()

    class Connection:
        cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

    result = MySqlOrderActualStartRepository(
        Connection()
    ).load_actual_start_query("CASE-DATE", for_update=False)

    assert result.case_no == "CASE-DATE"
    assert result.scheduling_version is None
    assert result.scheduling_generation is None
    assert result.client_finance_version is None
    assert result.payroll_version is None
    assert result.has_formal_assignments is False


def test_date_without_formal_assignment_is_not_projected_as_service_started() -> None:
    assert _service_started(date(2026, 9, 2), ()) is False
    assert _service_started(date(2026, 9, 2), (object(),)) is True


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
