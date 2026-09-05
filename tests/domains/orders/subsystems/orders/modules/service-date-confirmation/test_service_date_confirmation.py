"""
File: test_service_date_confirmation.py
Description: 驗證服務日期確認 Candidate、restart Scheduling handoff 與可選日期邊界。
"""

from datetime import date

import pytest

from domains.orders.service_date_confirmation import (
    ConfirmedServiceDateCandidate,
    group_service_dates_by_calendar_week,
)
from infrastructure.mysql.service_date_confirmation_repository import (
    MySqlServiceDateConfirmationRepository,
)
from subsystems.orders.service_date_confirmation_workflow import (
    RestartSchedulingAssignmentFacts,
    ServiceDateConfirmationFacts,
    ServiceDateConfirmationReceipt,
    ServiceDateConfirmationWorkflow,
    _candidate,
    _restart_scheduling_command,
)
class _UnitOfWork:
    committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.committed = True


class _RestartRepository:
    def __init__(self, facts):
        self.facts = facts
        self.commands = []
        self.replay_receipt = None

    def load(self, _case_no, *, lock=False):
        return self.facts

    def replay(self, _key, _fingerprint):
        return self.replay_receipt

    def save(self, candidate, **_kwargs):
        self.saved_receipt = ServiceDateConfirmationReceipt(
            candidate.case_no, 1, candidate.order_version,
            candidate.scheduling_version, candidate.service_dates,
            candidate.fingerprint,
        )
        return self.saved_receipt

    def persist_restarted_scheduling(self, command):
        self.commands.append(command)
        scheduling_version = command.candidate.resulting_aggregate_version
        saved = self.saved_receipt
        self.replay_receipt = ServiceDateConfirmationReceipt(
            saved.case_no,
            saved.confirmed_version,
            saved.order_version,
            scheduling_version,
            saved.service_dates,
            saved.fingerprint,
        )
        return scheduling_version


class _SnapshotInvalidation:
    def __init__(self):
        self.case_nos = []

    def invalidate_current_snapshot(self, case_no):
        self.case_nos.append(case_no)


class _EmptyRestartCursor:
    def __init__(self):
        self.statements = []

    def execute(self, statement, parameters):
        self.statements.append((statement, parameters))

    @staticmethod
    def fetchone():
        return None


def test_service_dates_must_match_the_contracted_day_count():
    with pytest.raises(ValueError, match="service date count"):
        ConfirmedServiceDateCandidate(
            "CASE-68",
            1,
            1,
            (date(2026, 8, 2),),
            2,
        )


def test_service_date_week_grouping_starts_on_sunday():
    weeks = group_service_dates_by_calendar_week(
        (date(2026, 8, 8), date(2026, 8, 9), date(2026, 8, 10))
    )

    assert weeks == (
        {
            "week_number": 1,
            "period_start": "2026-08-02",
            "period_end": "2026-08-08",
            "service_dates": ["2026-08-08"],
            "service_day_count": 1,
        },
        {
            "week_number": 2,
            "period_start": "2026-08-09",
            "period_end": "2026-08-15",
            "service_dates": ["2026-08-09", "2026-08-10"],
            "service_day_count": 2,
        },
    )


def test_service_date_must_be_in_the_server_selectable_range():
    facts = ServiceDateConfirmationFacts(
        "CASE-68", 1, 1, 2, (), (date(2026, 8, 1), date(2026, 8, 2)), None, ()
    )

    with pytest.raises(ValueError, match="outside_selectable_range"):
        _candidate(facts, (date(2026, 8, 1), date(2026, 8, 3)))


def test_restarted_historical_dates_build_one_canonical_scheduling_generation():
    facts = ServiceDateConfirmationFacts(
        "HIST-68", 3, 7, 2, (),
        (date(2026, 9, 3), date(2026, 9, 4)), None, (), 4,
        (RestartSchedulingAssignmentFacts(91, 12, 1, 0),),
    )

    command = _restart_scheduling_command(
        facts,
        (date(2026, 9, 3), date(2026, 9, 4)),
        actor="admin",
        reason="人工確認真實服務日期",
        idempotency_key="restart-dates-68",
        command_fingerprint="a" * 64,
        preview_fingerprint="b" * 64,
    )

    assert command.command_family == "historical_restart_service_dates"
    assert command.candidate.expected_aggregate_version == 7
    assert command.candidate.resulting_aggregate_version == 8
    assert command.candidate.generation_number == 5
    assignment = command.candidate.assignments[0]
    assert assignment.source_assignment_id == 91
    assert assignment.staff_id == 12
    assert assignment.service_dates == (date(2026, 9, 3), date(2026, 9, 4))
    assert assignment.assigned_start_date == date(2026, 9, 3)
    assert assignment.assigned_end_date == date(2026, 9, 4)


def test_restarted_multi_caregiver_dates_fail_closed_without_existing_allocation():
    facts = ServiceDateConfirmationFacts(
        "HIST-69", 3, 7, 2, (),
        (date(2026, 9, 3), date(2026, 9, 4)), None, (), 4,
        (
            RestartSchedulingAssignmentFacts(91, 12, 1, 0),
            RestartSchedulingAssignmentFacts(92, 13, 2, 0),
        ),
    )

    with pytest.raises(ValueError, match="historical_restart_assignment_allocation_required"):
        _restart_scheduling_command(
            facts,
            (date(2026, 9, 3), date(2026, 9, 4)),
            actor="admin",
            reason="人工確認真實服務日期",
            idempotency_key="restart-dates-69",
            command_fingerprint="a" * 64,
            preview_fingerprint="b" * 64,
        )


def test_restart_apply_persists_confirmed_dates_and_canonical_schedule_before_commit():
    facts = ServiceDateConfirmationFacts(
        "HIST-70", 3, 7, 2, (),
        (date(2026, 9, 3), date(2026, 9, 4)), None, (), 4,
        (RestartSchedulingAssignmentFacts(91, 12, 1, 0),),
    )
    repository = _RestartRepository(facts)
    invalidation = _SnapshotInvalidation()
    unit = _UnitOfWork()
    workflow = ServiceDateConfirmationWorkflow(repository, lambda: unit, invalidation)
    selected = (date(2026, 9, 3), date(2026, 9, 4))
    preview = workflow.preview(facts.case_no, selected)

    receipt = workflow.apply(
        facts.case_no,
        selected,
        expected_order_version=3,
        expected_scheduling_version=7,
        preview_fingerprint=preview.candidate.fingerprint.value,
        actor="admin",
        reason="人工確認真實服務日期",
        idempotency_key="restart-dates-70",
    )

    assert receipt.scheduling_version == 8
    assert len(repository.commands) == 1
    assert repository.commands[0].candidate.assignments[0].service_dates == selected
    assert invalidation.case_nos == ["HIST-70"]
    assert unit.committed is True


def test_restart_apply_replay_keeps_one_generation_and_same_scheduling_version():
    facts = ServiceDateConfirmationFacts(
        "HIST-71", 3, 7, 2, (),
        (date(2026, 9, 3), date(2026, 9, 4)), None, (), 4,
        (RestartSchedulingAssignmentFacts(91, 12, 1, 0),),
    )
    repository = _RestartRepository(facts)
    invalidation = _SnapshotInvalidation()
    workflow = ServiceDateConfirmationWorkflow(
        repository, _UnitOfWork, invalidation
    )
    selected = (date(2026, 9, 3), date(2026, 9, 4))
    preview = workflow.preview(facts.case_no, selected)
    arguments = dict(
        expected_order_version=3,
        expected_scheduling_version=7,
        preview_fingerprint=preview.candidate.fingerprint.value,
        actor="admin",
        reason="人工確認真實服務日期",
        idempotency_key="restart-dates-71",
    )

    first = workflow.apply(facts.case_no, selected, **arguments)
    replay = workflow.apply(facts.case_no, selected, **arguments)

    assert replay == first
    assert replay.scheduling_version == 8
    assert len(repository.commands) == 1
    assert invalidation.case_nos == ["HIST-71"]


def test_regular_service_date_apply_does_not_replace_scheduling():
    facts = ServiceDateConfirmationFacts(
        "CASE-72", 3, 7, 2, (),
        (date(2026, 9, 3), date(2026, 9, 4)), None, (),
    )
    repository = _RestartRepository(facts)
    invalidation = _SnapshotInvalidation()
    unit = _UnitOfWork()
    workflow = ServiceDateConfirmationWorkflow(repository, lambda: unit, invalidation)
    selected = (date(2026, 9, 3), date(2026, 9, 4))
    preview = workflow.preview(facts.case_no, selected)

    receipt = workflow.apply(
        facts.case_no,
        selected,
        expected_order_version=3,
        expected_scheduling_version=7,
        preview_fingerprint=preview.candidate.fingerprint.value,
        actor="admin",
        reason="一般服務日期確認",
        idempotency_key="regular-dates-72",
    )

    assert receipt.scheduling_version == 7
    assert repository.commands == []
    assert invalidation.case_nos == ["CASE-72"]
    assert unit.committed is True


def test_restart_detection_is_bound_to_the_current_generation_receipt():
    cursor = _EmptyRestartCursor()

    result = MySqlServiceDateConfirmationRepository._restart_scheduling_source(
        cursor, "HIST-73", 2
    )

    statement, parameters = cursor.statements[0]
    assert "restart_receipt.resulting_generation_id=generation.id" in statement
    assert (
        "restart_receipt.command_family='orders_historical_precision_restart'"
        in statement
    )
    assert "order_lifecycle_state_events" not in statement
    assert parameters == ("HIST-73",)
    assert result == (None, ())
