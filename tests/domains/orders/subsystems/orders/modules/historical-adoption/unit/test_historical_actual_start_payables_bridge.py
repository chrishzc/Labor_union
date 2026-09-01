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


def test_historical_rebuilder_uses_source_context_apply_entrypoint():
    calls = []
    service_dates = (date(2026, 8, 8), date(2026, 8, 11))

    class Planner:
        def calculate(self, _case_no, _actual_start_date, *, for_update):
            assert for_update is True
            return service_dates

        def prepare_source_generation(self, *_args, **_kwargs):
            calls.append("prepare")

    class ActualStart:
        def replay_from_immutable_source(self, _idempotency_key):
            return None

        def preview_historical_source(
            self,
            case_no,
            actual_start_date,
            *,
            recalculated_service_dates,
            source_staff_ids,
        ):
            calls.append(
                (
                    "preview_historical_source",
                    case_no,
                    actual_start_date,
                    recalculated_service_dates,
                    source_staff_ids,
                )
            )
            return SimpleNamespace(
                order_version=4,
                scheduling_version=5,
                client_finance_version=6,
                payroll_version=7,
                fingerprint=fingerprint_payload({"preview": "historical"}),
            )

        def apply_historical_source_in_current_unit_of_work(
            self,
            request,
            *,
            recalculated_service_dates,
            source_staff_ids,
        ):
            calls.append(
                (
                    "apply_historical_source",
                    request,
                    recalculated_service_dates,
                    source_staff_ids,
                )
            )

    HistoricalActualStartRebuilder(ActualStart(), Planner()).apply_in_current_unit_of_work(
        case_no="CASE-1",
        actual_start_date=date(2026, 8, 8),
        source_identity="historical-orders:digest:row:source-context",
        actor="test-operator",
        correlation_id="historical-rebuild-source-context",
        source_staff_ids=(11,),
    )

    assert calls[0] == "prepare"
    assert calls[1] == (
        "preview_historical_source",
        "CASE-1",
        date(2026, 8, 8),
        service_dates,
        (11,),
    )
    assert calls[2][0] == "apply_historical_source"
    assert calls[2][1].expected_order_version.value == 4
    assert calls[2][2:] == (service_dates, (11,))


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
        def __init__(self):
            self.calls = []

        def preview_historical_source(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    actual_start = ActualStart()
    HistoricalActualStartRebuilder(actual_start, Planner()).preview(
        case_no="CASE-1",
        actual_start_date=date(2026, 8, 8),
        correlation_id="historical-preview-staff-conflict",
    )

    assert actual_start.calls == [
        (
            ("CASE-1", date(2026, 8, 8)),
            {
                "recalculated_service_dates": (date(2026, 8, 8),),
                "source_staff_ids": (),
            },
        )
    ]


def test_mysql_historical_planner_apply_reuses_an_effective_generation():
    from infrastructure.mysql.historical_actual_start_date_planner import (
        MySqlHistoricalActualStartDatePlanner,
    )

    class Cursor:
        def __init__(self):
            self.statements = []
            self.rows = iter(
                (
                    {
                        "aggregate_version": 3,
                        "generation_counter": 3,
                        "effective_generation_id": 114,
                    },
                    {"id": 51},
                )
            )

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _parameters):
            self.statements.append(statement)

        def fetchone(self):
            return next(self.rows)

    cursor = Cursor()
    connection = SimpleNamespace(cursor=lambda: cursor)

    MySqlHistoricalActualStartDatePlanner(connection).prepare_source_generation(
        "CASE-1",
        (date(2026, 8, 8),),
        source_identity="source:row:70",
        actor="test-operator",
        correlation_id="historical-existing-generation",
    )

    assert len(cursor.statements) == 2
    assert all(
        statement.lstrip().upper().startswith("SELECT")
        for statement in cursor.statements
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


def test_historical_planner_bootstraps_when_effective_generation_is_empty(monkeypatch):
    import infrastructure.mysql.historical_actual_start_date_planner as planner
    from domains.scheduling.generation import SchedulingGenerationCandidate

    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    cursor = Cursor()
    connection = SimpleNamespace(cursor=lambda: cursor)
    aggregate = {
        "aggregate_version": 4,
        "generation_counter": 7,
        "effective_generation_id": 71,
    }
    candidate = SchedulingGenerationCandidate(
        case_no="CASE-1",
        generation_number=8,
        expected_aggregate_version=4,
        resulting_aggregate_version=5,
        cancelled_assignment_ids=(),
        assignments=(),
        buffers=(),
    )
    monkeypatch.setattr(planner, "_locked_or_bootstrapped_aggregate", lambda *_args: aggregate)
    monkeypatch.setattr(
        planner,
        "_source_assignment_and_order_facts",
        lambda *_args, **_kwargs: (
            ({"id": 9, "staff_id": 11},),
            {"service_hours_per_day": 8, "lifecycle_version": 9},
        ),
    )
    monkeypatch.setattr(planner, "_bootstrap_candidate", lambda *_args: candidate)
    monkeypatch.setattr(
        planner,
        "_effective_generation_has_assignments",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        planner,
        "_case_payroll_policy",
        lambda *_args, **_kwargs: {"policy_version": 1},
    )
    monkeypatch.setattr(
        planner,
        "_effective_generation_assignment_ids",
        lambda *_args: (),
    )
    monkeypatch.setattr(
        planner,
        "persist_scheduling_replacement",
        lambda _cursor, command: calls.append(command),
    )
    monkeypatch.setattr(planner, "_persist_rate_snapshots", lambda *_args: None)

    planner.MySqlHistoricalActualStartDatePlanner(connection).prepare_source_generation(
        "CASE-1",
        (date(2026, 8, 8),),
        source_identity="historical-orders:digest:row:8",
        actor="historical-import",
        correlation_id="historical-override-test",
    )

    command = calls[0]
    assert command.candidate.cancelled_assignment_ids == ()
    assert command.candidate.case_no == "CASE-1"
    assert command.candidate.generation_number == 8


def test_historical_planner_maps_effective_staff_date_duplicate_to_preparation_blocker(
    monkeypatch,
):
    from pymysql.err import IntegrityError

    import infrastructure.mysql.historical_actual_start_date_planner as planner
    from domains.scheduling.generation import SchedulingGenerationCandidate

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    cursor = Cursor()
    connection = SimpleNamespace(cursor=lambda: cursor)
    candidate = SchedulingGenerationCandidate(
        case_no="CASE-1",
        generation_number=1,
        expected_aggregate_version=0,
        resulting_aggregate_version=1,
        cancelled_assignment_ids=(),
        assignments=(),
        buffers=(),
    )
    monkeypatch.setattr(
        planner,
        "_locked_or_bootstrapped_aggregate",
        lambda *_args: {
            "aggregate_version": 0,
            "generation_counter": 0,
            "effective_generation_id": None,
        },
    )
    monkeypatch.setattr(
        planner,
        "_effective_generation_has_assignments",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        planner,
        "_source_assignment_and_order_facts",
        lambda *_args, **_kwargs: (
            ({"id": 9, "staff_id": 11},),
            {"lifecycle_version": 1, "service_hours_per_day": 8},
        ),
    )
    monkeypatch.setattr(planner, "_bootstrap_candidate", lambda *_args: candidate)
    monkeypatch.setattr(planner, "_effective_generation_assignment_ids", lambda *_args: ())
    monkeypatch.setattr(
        planner,
        "_case_payroll_policy",
        lambda *_args, **_kwargs: {"policy_version": 1},
    )

    def raise_duplicate(*_args):
        raise IntegrityError(
            1062,
            "Duplicate entry '11-2026-08-08-1' for key "
            "'staff_schedule.uq_staff_schedule_effective_date'",
        )

    monkeypatch.setattr(planner, "persist_scheduling_replacement", raise_duplicate)

    with pytest.raises(HistoricalActualStartPreparationError) as caught:
        planner.MySqlHistoricalActualStartDatePlanner(connection).prepare_source_generation(
            "CASE-1",
            (date(2026, 8, 8),),
            source_identity="historical-orders:digest:row:staff-conflict",
            actor="historical-import",
            correlation_id="historical-staff-conflict",
        )

    assert caught.value.code == "historical_actual_start_staff_schedule_conflict"


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
