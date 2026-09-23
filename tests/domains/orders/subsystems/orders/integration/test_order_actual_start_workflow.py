"""
File: test_order_actual_start_workflow.py
Description: 驗證實際開工 command 契約及非 AutoComplete workflow 的 lifecycle 邊界。
"""

from dataclasses import replace
from datetime import date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
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
    calculate_progressive_segment_service_dates,
    date_bound_manual_overrides,
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
from infrastructure.mysql.payroll_terms_writer import (
    load_actual_start_source_rate_snapshots,
    persist_actual_start_rate_snapshot_carry,
)
from infrastructure.mysql.scheduling_replacement_writer import (
    _preserve_previous_leave_occupancy,
)
from api.dependencies.order_actual_start import ActualStartApplication
from api.routes.order_actual_start import _raise_value_error


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


def test_restarted_historical_tombstone_uses_date_only_route() -> None:
    query = ActualStartQueryFacts(
        "CASE-1", None, date(2026, 8, 1), False, 1,
        2, None, 3, 4, False, True,
    )

    class Repository:
        def load_actual_start_query(self, case_no, *, for_update):
            assert case_no == "CASE-1"
            assert for_update is False
            return query

    calls = []

    class Workflow:
        def preview_date_only(self, facts, actual_start_date):
            calls.append(("preview_date_only", facts, actual_start_date))
            return "date-only-preview"

        def apply_date_only(self, request):
            calls.append(("apply_date_only", request))
            return "date-only-receipt"

        def preview(self, *_args, **_kwargs):
            raise AssertionError("unassigned historical order must not reschedule")

        def apply(self, *_args, **_kwargs):
            raise AssertionError("unassigned historical order must not reschedule")

    application = ActualStartApplication(Repository(), Workflow())

    assert application.preview("CASE-1", date(2026, 8, 3)) == "date-only-preview"
    request = ActualStartDateOnlyApplyRequest(
        "CASE-1", date(2026, 8, 3), ExpectedVersion(1),
        PreviewFingerprint("a" * 64), CorrelationId("date-only"),
    )
    assert application.apply(request) == "date-only-receipt"
    assert calls == [
        ("preview_date_only", query, date(2026, 8, 3)),
        ("apply_date_only", request),
    ]


def test_restarted_tombstone_rejects_stale_reschedule_apply_mode() -> None:
    query = ActualStartQueryFacts(
        "CASE-1", None, date(2026, 8, 1), False, 1,
        2, None, 3, 4, False, True,
    )

    class Repository:
        def load_actual_start_query(self, *_args, **_kwargs):
            return query

    class Workflow:
        def apply(self, *_args):
            raise AssertionError("unassigned case must not enter reschedule")

    with pytest.raises(ActualStartWorkflowError) as error:
        ActualStartApplication(Repository(), Workflow()).apply(_request())
    assert error.value.error.code == "actual_start_mode_changed"


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


def test_actual_start_recalculates_each_segment_from_previous_end() -> None:
    assignments = (
        ActualStartAssignmentFacts(
            11, 21, 1, date(2026, 8, 3), date(2026, 8, 4),
            (date(2026, 8, 3), date(2026, 8, 4)),
        ),
        ActualStartAssignmentFacts(
            12, 22, 2, date(2026, 8, 5), date(2026, 8, 6),
            (date(2026, 8, 5), date(2026, 8, 6)),
        ),
    )
    recalculated = calculate_progressive_segment_service_dates(
        date(2026, 9, 6), assignments, "週休2日", (date(2026, 9, 7),),
    )
    candidate = build_actual_start_candidate(
        ActualStartOrderFacts(
            "CASE-SEGMENTS", 3, None, False, ServiceTimeTerms(None, None, None),
        ),
        ActualStartSchedulingFacts(
            "CASE-SEGMENTS", 5, 1, date(2026, 8, 3), assignments,
        ),
        date(2026, 9, 6), 8, recalculated,
    )

    assert recalculated == (
        date(2026, 9, 8), date(2026, 9, 9),
        date(2026, 9, 10), date(2026, 9, 11),
    )
    assert [
        (item.source_assignment_id, item.staff_id, item.sequence,
         item.assigned_start_date, item.assigned_end_date, item.service_dates)
        for item in candidate.assignments
    ] == [
        (11, 21, 1, date(2026, 9, 6), date(2026, 9, 9), recalculated[:2]),
        (12, 22, 2, date(2026, 9, 10), date(2026, 9, 11), recalculated[2:]),
    ]


def test_actual_start_recalculates_around_effective_leave_per_caregiver() -> None:
    assignments = (
        ActualStartAssignmentFacts(
            11, 21, 1, date(2026, 8, 3), date(2026, 8, 4),
            (date(2026, 8, 3), date(2026, 8, 4)),
        ),
        ActualStartAssignmentFacts(
            12, 22, 2, date(2026, 8, 5), date(2026, 8, 6),
            (date(2026, 8, 5), date(2026, 8, 6)),
        ),
    )
    assert calculate_progressive_segment_service_dates(
        date(2026, 9, 8), assignments, "連續服務", (),
        ((21, date(2026, 9, 8)), (22, date(2026, 9, 11))),
    ) == (
        date(2026, 9, 9), date(2026, 9, 10),
        date(2026, 9, 12), date(2026, 9, 13),
    )


def test_actual_start_preserves_leave_occupancy_only_for_valid_successor() -> None:
    class Cursor:
        def __init__(self):
            self.statements = []
            self.rowcount = 0

        def execute(self, sql, parameters):
            self.statements.append((sql, parameters))
            self.rowcount = 1 if sql.startswith("UPDATE") else 0

        def fetchall(self):
            return ({
                "staff_id": 21,
                "occupancy_date": date(2026, 9, 8),
                "resulting_staff_id": 22,
                "resulting_service_date": date(2026, 9, 10),
            },)

    valid = SimpleNamespace(candidate=SimpleNamespace(assignments=(
        SimpleNamespace(staff_id=21, service_dates=(date(2026, 9, 9),)),
        SimpleNamespace(staff_id=22, service_dates=(date(2026, 9, 10),)),
    )))
    cursor = Cursor()
    _preserve_previous_leave_occupancy(cursor, valid, 7, 8)
    assert cursor.statements[-1] == (
        "UPDATE scheduling_leave_occupancy_days SET generation_id=%s "
        "WHERE generation_id=%s AND active_marker=1",
        (8, 7),
    )
    invalid = SimpleNamespace(candidate=SimpleNamespace(assignments=(
        SimpleNamespace(staff_id=21, service_dates=(date(2026, 9, 8),)),
        SimpleNamespace(staff_id=22, service_dates=(date(2026, 9, 10),)),
    )))
    with pytest.raises(ValueError, match="actual_start_leave_outcome_conflict"):
        _preserve_previous_leave_occupancy(Cursor(), invalid, 7, 8)


def test_actual_start_leave_outcome_conflict_is_typed_409() -> None:
    with pytest.raises(HTTPException) as caught:
        _raise_value_error(
            ValueError("actual_start_leave_outcome_conflict"),
            CorrelationId("actual-start-leave-test"),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["error"]["code"] == "actual_start_leave_outcome_conflict"


def test_actual_start_rate_snapshots_are_copied_exactly_without_payroll_root_write() -> None:
    class Cursor:
        statements = []

        def execute(self, sql, args):
            self.statements.append((sql, args))

        def fetchall(self):
            source_id = self.statements[-1][1][0]
            return ({
                "policy_version": 7,
                "policy_kind": "municipal",
                "hourly_rate_ntd": 380 if source_id == 11 else 420,
            },)

        def executemany(self, sql, rows):
            self.statements.append((sql, rows))

    assignments = (
        SimpleNamespace(
            source_assignment_id=11,
            lineage_source_assignment_ids=(11,),
            candidate_key="a1",
        ),
        SimpleNamespace(
            source_assignment_id=12,
            lineage_source_assignment_ids=(12,),
            candidate_key="a2",
        ),
    )
    cursor = Cursor()
    command = SimpleNamespace(candidate=SimpleNamespace(assignments=assignments))
    result = SimpleNamespace(assignment_resolution=SimpleNamespace(
        assignment_id_by_candidate_key={"a1": 101, "a2": 102},
    ))
    persist_actual_start_rate_snapshot_carry(cursor, command, result)

    assert cursor.statements[-1][1] == (
        (101, 7, "municipal", 380, "carried-from:11"),
        (102, 7, "municipal", 420, "carried-from:12"),
    )
    assert all(
        "payroll_case_accounts" not in sql and "staff_obligations" not in sql
        for sql, _ in cursor.statements
    )
    with pytest.raises(ValueError, match="lineage_invalid"):
        load_actual_start_source_rate_snapshots(
            cursor,
            (SimpleNamespace(source_assignment_id=None,
                             lineage_source_assignment_ids=()),),
            lock=False,
        )


def test_actual_start_mysql_calculator_uses_one_locked_holiday_snapshot_for_segments() -> None:
    statements = []
    mode = ["週休二日"]
    leave_rows = []
    confirmation = [None]
    confirmed_days = [date(2026, 8, 3), date(2026, 8, 4)]

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, parameters):
            statements.append((sql, parameters))

        def fetchone(self):
            if "FROM confirmed_service_date_versions" in statements[-1][0]:
                return confirmation[0]
            return {"service_type": mode[0]}

        def fetchall(self):
            if "FROM confirmed_service_date_days" in statements[-1][0]:
                return tuple({"service_date": day} for day in confirmed_days)
            if "FROM holidays" not in statements[-1][0]:
                return tuple(leave_rows)
            return ({
                "holiday_date": date(2026, 9, 7),
                "holiday_name": "休假",
                "is_double_pay_default": 0,
            },)

    class Connection:
        def cursor(self):
            return Cursor()

    assignment = ActualStartAssignmentFacts(
        11, 21, 1, date(2026, 8, 3), date(2026, 8, 4),
        (date(2026, 8, 3), date(2026, 8, 4)),
    )
    dates, version = MySqlOrderActualStartRepository(Connection()).calculate_progressive_service_dates(
        "CASE-CALENDAR", date(2026, 9, 6), (assignment,), lock=True,
    )
    assert dates == (date(2026, 9, 8), date(2026, 9, 9))
    assert len(version) == 64
    assert all("FOR UPDATE" in sql for sql, _ in statements)
    mode[0] = "休周日"
    same_dates, changed_version = MySqlOrderActualStartRepository(Connection()).calculate_progressive_service_dates(
        "CASE-CALENDAR", date(2026, 9, 8), (assignment,), lock=True,
    )
    mode[0] = "週休二日"
    _, original_rule_version = MySqlOrderActualStartRepository(Connection()).calculate_progressive_service_dates(
        "CASE-CALENDAR", date(2026, 9, 8), (assignment,), lock=True,
    )
    assert same_dates == (date(2026, 9, 8), date(2026, 9, 9))
    assert changed_version != original_rule_version

    confirmation[0] = {
        "id": 42, "version": 1, "service_day_count": 2,
        "service_date_fingerprint": "a" * 64,
    }
    _, confirmed_version = MySqlOrderActualStartRepository(Connection()).calculate_progressive_service_dates(
        "CASE-CALENDAR", date(2026, 9, 8), (assignment,), lock=True,
    )
    confirmation[0] = {**confirmation[0], "version": 2}
    _, changed_confirmation_version = MySqlOrderActualStartRepository(Connection()).calculate_progressive_service_dates(
        "CASE-CALENDAR", date(2026, 9, 8), (assignment,), lock=True,
    )
    assert confirmed_version != changed_confirmation_version
    assert any("confirmed_service_date_days" in sql and "FOR UPDATE" in sql for sql, _ in statements)
    confirmed_days[1] = date(2026, 8, 5)
    _, changed_confirmation_dates = MySqlOrderActualStartRepository(Connection()).calculate_progressive_service_dates(
        "CASE-CALENDAR", date(2026, 9, 8), (assignment,), lock=True,
    )
    assert changed_confirmation_dates != changed_confirmation_version

    confirmed_days[:] = [date(2026, 9, 7), date(2026, 9, 8)]
    holiday_work_assignment = ActualStartAssignmentFacts(
        12, 21, 1, date(2026, 9, 7), date(2026, 9, 8),
        (date(2026, 9, 7), date(2026, 9, 8)),
    )
    confirmed_work_dates, _ = MySqlOrderActualStartRepository(Connection()).calculate_progressive_service_dates(
        "CASE-CALENDAR", date(2026, 9, 7), (holiday_work_assignment,), lock=True,
    )
    assert confirmed_work_dates == (date(2026, 9, 7), date(2026, 9, 8))
    confirmation[0] = None
    with pytest.raises(ValueError, match="actual_start_manual_work_confirmation_required"):
        MySqlOrderActualStartRepository(Connection()).calculate_progressive_service_dates(
            "CASE-CALENDAR", date(2026, 9, 7), (holiday_work_assignment,), lock=True,
        )

    mode[0] = "連續服務"
    leave_rows.append({
        "id": 101,
        "outcome_id": 201,
        "staff_id": 21,
        "occupancy_date": date(2026, 9, 8),
        "resolution_type": "defer_following_assignments",
        "resulting_staff_id": 21,
        "resulting_service_date": date(2026, 9, 10),
    })
    leave_dates, leave_version = MySqlOrderActualStartRepository(Connection()).calculate_progressive_service_dates(
        "CASE-CALENDAR", date(2026, 9, 8), (assignment,), lock=True,
    )
    assert leave_dates == (date(2026, 9, 9), date(2026, 9, 10))
    assert leave_version != original_rule_version
    leave_rows[0] = {**leave_rows[0], "resulting_service_date": date(2026, 9, 11)}
    with pytest.raises(ValueError, match="actual_start_leave_outcome_conflict"):
        MySqlOrderActualStartRepository(Connection()).calculate_progressive_service_dates(
            "CASE-CALENDAR", date(2026, 9, 8), (assignment,), lock=True,
        )


def test_actual_start_preserves_only_same_date_same_staff_manual_choices() -> None:
    source = (
        ActualStartAssignmentFacts(
            11, 21, 1, date(2026, 9, 6), date(2026, 9, 8),
            (date(2026, 9, 6), date(2026, 9, 8)),
        ),
        ActualStartAssignmentFacts(
            12, 22, 2, date(2026, 9, 9), date(2026, 9, 11),
            (date(2026, 9, 9), date(2026, 9, 11)),
        ),
    )
    holidays = (date(2026, 9, 7),)
    work, rest = date_bound_manual_overrides(
        source, "休周日", holidays,
        (date(2026, 9, 6), date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 11)),
        date(2026, 9, 6), date(2026, 10, 1),
    )
    assert work == ((21, date(2026, 9, 6)),)
    assert rest == ((22, date(2026, 9, 10)),)
    assert calculate_progressive_segment_service_dates(
        date(2026, 9, 6), source, "休周日", holidays, (), work, rest,
    ) == (
        date(2026, 9, 6), date(2026, 9, 8),
        date(2026, 9, 9), date(2026, 9, 11),
    )
    assert calculate_progressive_segment_service_dates(
        date(2026, 9, 7), source, "休周日", holidays, (), work, rest,
    ) == (
        date(2026, 9, 8), date(2026, 9, 9),
        date(2026, 9, 11), date(2026, 9, 12),
    )
    assert calculate_progressive_segment_service_dates(
        date(2026, 9, 6), source, "休周日", holidays,
        ((21, date(2026, 9, 6)),), work, rest,
    ) == (
        date(2026, 9, 8), date(2026, 9, 9),
        date(2026, 9, 11), date(2026, 9, 12),
    )


def test_actual_start_holiday_work_is_not_shifted_to_new_date() -> None:
    source = (ActualStartAssignmentFacts(
        11, 21, 1, date(2026, 9, 7), date(2026, 9, 8),
        (date(2026, 9, 7), date(2026, 9, 8)),
    ),)
    holidays = (date(2026, 9, 7), date(2026, 9, 10))
    work, rest = date_bound_manual_overrides(
        source, "連續服務", holidays,
        (date(2026, 9, 7), date(2026, 9, 8)),
        date(2026, 9, 7), date(2026, 9, 30),
    )
    assert work == ((21, date(2026, 9, 7)),)
    assert rest == ()
    assert calculate_progressive_segment_service_dates(
        date(2026, 9, 10), source, "連續服務", holidays, (), work, rest,
    ) == (date(2026, 9, 11), date(2026, 9, 12))

    with pytest.raises(ValueError, match="actual_start_manual_work_confirmation_required"):
        date_bound_manual_overrides(
            source, "連續服務", holidays, (),
            date(2026, 9, 7), date(2026, 9, 30),
        )
    with pytest.raises(HTTPException) as caught:
        _raise_value_error(
            ValueError("actual_start_manual_work_confirmation_required"),
            CorrelationId("unconfirmed-holiday-work"),
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["error"]["code"] == "actual_start_manual_work_confirmation_required"


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
