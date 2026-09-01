from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from shared_kernel.errors import ErrorCategory
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders.historical_actual_start_rebuild import (
    HistoricalActualStartPreparationError,
    HistoricalActualStartRebuilder,
)
from subsystems.orders.actual_start_workflow import ActualStartWorkflowError
from subsystems.payroll.terms_impact import PayrollTermsSourceFacts


def test_historical_rebuilder_prepares_source_generation_before_preview():
    calls = []

    class Planner:
        def calculate(self, case_no, actual_start_date, *, for_update):
            assert (case_no, actual_start_date, for_update) == (
                "CASE-1",
                date(2026, 8, 8),
                True,
            )
            return (date(2026, 8, 8), date(2026, 8, 11))

        def prepare_source_generation(
            self,
            case_no,
            service_dates,
            *,
            source_identity,
            actor,
            correlation_id,
        ):
            calls.append(
                (
                    "prepare",
                    case_no,
                    service_dates,
                    source_identity,
                    actor,
                    correlation_id,
                )
            )

    class ActualStart:
        def replay_from_immutable_source(self, _idempotency_key):
            return None

        def preview(self, case_no, actual_start_date, *, recalculated_service_dates):
            assert calls and calls[0][0] == "prepare"
            calls.append(("preview", case_no, actual_start_date, recalculated_service_dates))
            return SimpleNamespace(
                order_version=4,
                scheduling_version=5,
                client_finance_version=6,
                payroll_version=7,
                fingerprint=fingerprint_payload({"preview": "historical"}),
            )

        def apply_in_current_unit_of_work(self, request, *, recalculated_service_dates):
            calls.append(("apply", request.case_no, recalculated_service_dates))

    HistoricalActualStartRebuilder(ActualStart(), Planner()).apply_in_current_unit_of_work(
        case_no="CASE-1",
        actual_start_date=date(2026, 8, 8),
        source_identity="historical-orders:digest:row:5",
        actor="test-operator",
        correlation_id="historical-rebuild-correlation",
    )

    assert [item[0] for item in calls] == ["prepare", "preview", "apply"]


def test_historical_rebuilder_replays_completed_actual_start_before_recomputing_versions():
    calls = []

    class Planner:
        def calculate(self, case_no, actual_start_date, *, for_update):
            calls.append(("calculate", case_no, actual_start_date, for_update))
            return (date(2026, 8, 8), date(2026, 8, 11))

        def prepare_source_generation(self, *_args, **_kwargs):
            raise AssertionError("completed replay must not bootstrap scheduling again")

    class ActualStart:
        def replay_from_immutable_source(self, idempotency_key):
            calls.append(("replay", idempotency_key.value))
            return SimpleNamespace(order_version=9)

        def preview(self, *_args, **_kwargs):
            raise AssertionError("completed replay must not build a new Actual Start command")

    HistoricalActualStartRebuilder(ActualStart(), Planner()).apply_in_current_unit_of_work(
        case_no="CASE-1",
        actual_start_date=date(2026, 8, 8),
        source_identity="historical-orders:digest:row:5",
        actor="test-operator",
        correlation_id="historical-rebuild-replay",
    )

    assert calls[0] == ("calculate", "CASE-1", date(2026, 8, 8), True)
    assert calls[1][0] == "replay"
    assert calls[1][1].startswith("historical-actual-start:")


def test_historical_rebuilder_preview_reports_missing_historical_assignment_as_blocker():
    class Planner:
        def calculate(self, case_no, actual_start_date, *, for_update):
            assert (case_no, actual_start_date, for_update) == (
                "CASE-1",
                date(2026, 8, 8),
                False,
            )
            return (date(2026, 8, 8),)

        def preview_source_generation(self, case_no, service_dates):
            assert (case_no, service_dates) == ("CASE-1", (date(2026, 8, 8),))
            raise HistoricalActualStartPreparationError(
                "historical_assignment_required_for_actual_start"
            )

    class ActualStart:
        def preview(self, *_args, **_kwargs):
            raise AssertionError("blocked preparation must stop before Actual Start preview")

    with pytest.raises(ActualStartWorkflowError) as caught:
        HistoricalActualStartRebuilder(ActualStart(), Planner()).preview(
            case_no="CASE-1",
            actual_start_date=date(2026, 8, 8),
            correlation_id="historical-preview-blocker",
        )

    assert caught.value.error.category is ErrorCategory.DOMAIN_BLOCKED
    assert caught.value.error.code == "historical_assignment_required_for_actual_start"
    assert caught.value.error.domain_blockers == (
        "historical_assignment_required_for_actual_start",
    )


def test_historical_rebuilder_preview_allows_existing_staff_schedule_for_source_override():
    class Planner:
        def calculate(self, _case_no, _actual_start_date, *, for_update):
            assert for_update is False
            return (date(2026, 8, 8),)

        def preview_source_generation(self, _case_no, _service_dates):
            return None

    class ActualStart:
        def preview(self, *_args, **_kwargs):
            return None

    HistoricalActualStartRebuilder(ActualStart(), Planner()).preview(
        case_no="CASE-1",
        actual_start_date=date(2026, 8, 8),
        correlation_id="historical-preview-staff-conflict",
    )


def test_mysql_historical_planner_preview_checks_assignment_before_any_write():
    from infrastructure.mysql.historical_actual_start_date_planner import (
        MySqlHistoricalActualStartDatePlanner,
    )

    class Cursor:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _parameters):
            self.statements.append(statement)

        def fetchone(self):
            return None

        def fetchall(self):
            return ()

    cursor = Cursor()
    connection = SimpleNamespace(cursor=lambda: cursor)

    with pytest.raises(HistoricalActualStartPreparationError) as caught:
        MySqlHistoricalActualStartDatePlanner(connection).preview_source_generation(
            "CASE-1",
            (date(2026, 8, 8),),
        )

    assert caught.value.code == "historical_assignment_required_for_actual_start"
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in cursor.statements)


def test_mysql_historical_planner_preview_does_not_block_existing_staff_schedule():
    from infrastructure.mysql.historical_actual_start_date_planner import (
        MySqlHistoricalActualStartDatePlanner,
    )

    class Cursor:
        def __init__(self):
            self.statements = []
            self.one_rows = iter(
                (
                    {
                        "aggregate_version": 0,
                        "generation_counter": 0,
                        "effective_generation_id": None,
                    },
                    {"lifecycle_version": 3, "service_hours_per_day": 8},
                    {
                        "policy_version": 1,
                        "policy_kind": "fixed",
                        "hourly_rate_ntd": 300,
                        "source_identity_status": "verified",
                    },
                )
            )

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _parameters):
            self.statements.append(statement)

        def fetchone(self):
            return next(self.one_rows)

        def fetchall(self):
            return (
                {
                    "id": 91,
                    "staff_id": 11,
                    "assignment_sequence": 1,
                    "assigned_start_date": date(2026, 8, 8),
                    "assigned_end_date": date(2026, 8, 8),
                },
            )

    cursor = Cursor()
    connection = SimpleNamespace(cursor=lambda: cursor)

    MySqlHistoricalActualStartDatePlanner(connection).preview_source_generation(
        "CASE-1",
        (date(2026, 8, 8),),
    )
    assert all(
        statement.lstrip().upper().startswith("SELECT")
        for statement in cursor.statements
    )


def test_historical_planner_limits_source_override_to_conflicting_schedule_dates():
    from infrastructure.mysql.historical_actual_start_date_planner import (
        _schedule_overlap_predicates,
    )
    from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate

    candidate = SchedulingGenerationCandidate(
        case_no="CASE-1",
        generation_number=1,
        expected_aggregate_version=0,
        resulting_aggregate_version=1,
        cancelled_assignment_ids=(),
        assignments=(
            AssignmentCandidate(
                candidate_key="CASE-1:historical:g1:a1",
                source_assignment_id=9,
                staff_id=11,
                sequence=1,
                assigned_start_date=date(2026, 8, 8),
                assigned_end_date=date(2026, 8, 12),
                service_dates=(date(2026, 8, 8), date(2026, 8, 12)),
                actual_hours=16,
            ),
        ),
        buffers=(),
    )

    predicates, parameters = _schedule_overlap_predicates(candidate)

    assert predicates == ("(staff_id=%s AND work_date IN (%s,%s))",)
    assert parameters == (11, date(2026, 8, 8), date(2026, 8, 12))


def test_historical_planner_deletes_only_conflicting_current_schedule_projections():
    from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
    from infrastructure.mysql.historical_actual_start_date_planner import (
        _replace_conflicting_current_schedule_state,
    )

    class Cursor:
        def __init__(self):
            self.statements = []

        def execute(self, statement, parameters):
            self.statements.append((statement, parameters))

    candidate = SchedulingGenerationCandidate(
        case_no="CASE-1",
        generation_number=1,
        expected_aggregate_version=0,
        resulting_aggregate_version=1,
        cancelled_assignment_ids=(),
        assignments=(
            AssignmentCandidate(
                candidate_key="CASE-1:historical:g1:a1",
                source_assignment_id=9,
                staff_id=11,
                sequence=1,
                assigned_start_date=date(2026, 8, 8),
                assigned_end_date=date(2026, 8, 12),
                service_dates=(date(2026, 8, 8), date(2026, 8, 12)),
                actual_hours=16,
            ),
        ),
        buffers=(),
    )
    cursor = Cursor()

    _replace_conflicting_current_schedule_state(cursor, "CASE-1", candidate)

    assert len(cursor.statements) == 2
    occupancy_statement, occupancy_parameters = cursor.statements[0]
    schedule_statement, schedule_parameters = cursor.statements[1]
    assert occupancy_statement.startswith("DELETE FROM scheduling_effective_occupancy")
    assert occupancy_parameters == (
        11,
        date(2026, 8, 8),
        date(2026, 8, 12),
    )
    assert schedule_statement.startswith("DELETE FROM staff_schedule")
    assert "case_no<>%s" in schedule_statement
    assert schedule_parameters == (
        "CASE-1",
        11,
        date(2026, 8, 8),
        date(2026, 8, 12),
    )


def test_historical_planner_deletes_unmanaged_schedules_for_the_same_case():
    from infrastructure.mysql.historical_actual_start_date_planner import (
        _delete_unmanaged_case_schedules,
    )

    class Cursor:
        def __init__(self):
            self.statement = None
            self.parameters = None

        def execute(self, statement, parameters):
            self.statement = statement
            self.parameters = parameters

    cursor = Cursor()

    _delete_unmanaged_case_schedules(cursor, "CASE-1")

    assert cursor.parameters == ("CASE-1",)
    assert cursor.statement.startswith("DELETE FROM staff_schedule")
    assert "case_no=%s" in cursor.statement
    assert "generation_id IS NULL" in cursor.statement


def test_historical_bootstrap_single_assignment_uses_recalculated_service_dates():
    from infrastructure.mysql.historical_actual_start_date_planner import (
        _bootstrap_candidate,
    )

    source = ({
        "id": 91,
        "staff_id": 11,
        "assignment_sequence": 8,
        "assigned_start_date": date(2026, 8, 8),
        "assigned_end_date": date(2026, 8, 9),
    },)
    service_dates = (
        date(2026, 8, 8),
        date(2026, 8, 11),
        date(2026, 8, 12),
    )

    candidate = _bootstrap_candidate(
        "CASE-1",
        {
            "aggregate_version": 0,
            "generation_counter": 0,
            "effective_generation_id": None,
        },
        source,
        service_dates,
        8,
    )

    assignment = candidate.assignments[0]
    assert assignment.source_assignment_id == 91
    assert assignment.sequence == 1
    assert assignment.service_dates == service_dates
    assert assignment.assigned_end_date == date(2026, 8, 12)
    assert assignment.actual_hours == 24
    assert candidate.resulting_aggregate_version == 1


def test_actual_start_payroll_impact_receives_recalculated_due_date(monkeypatch):
    import subsystems.orders.actual_start_workflow as workflow

    captured = {}

    def capture(source, scheduling, order_terms, change_identity):
        captured["source"] = source
        captured["scheduling"] = scheduling
        captured["order_terms"] = order_terms
        captured["change_identity"] = change_identity
        return "payroll-candidate"

    monkeypatch.setattr(workflow, "build_payroll_terms_impact", capture)
    source = PayrollTermsSourceFacts(
        case_no="CASE-1",
        payroll_version=0,
        source_terms=(),
        existing_obligations=(),
        staff_payment_due_date=None,
    )
    order_terms = object()
    facts = SimpleNamespace(
        payroll=source,
        order=SimpleNamespace(terms=order_terms),
    )
    due_date = date(2026, 10, 15)
    scheduling = object()

    result = workflow._payroll_impact(
        facts,
        scheduling,
        "actual-start:test",
        due_date,
    )

    assert result == "payroll-candidate"
    assert captured["source"].staff_payment_due_date == due_date
    assert captured["scheduling"] is scheduling
    assert captured["order_terms"] is order_terms
