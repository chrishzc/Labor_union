"""
File: test_service_date_confirmation.py
Description: 驗證服務日期確認 Candidate、歷史 tombstone 日期-only 與可選日期邊界。
"""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier, Lock

import pytest

from domains.orders.service_date_confirmation import (
    ConfirmedServiceDateCandidate,
    group_service_dates_by_calendar_week,
)
from infrastructure.mysql.service_date_confirmation_repository import (
    MySqlServiceDateConfirmationRepository,
)
from infrastructure.mysql.payroll_terms_writer import (
    load_historical_restart_arrangement_rates,
)
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.historical_restart_arrangement import (
    ArrangementSegmentIntent,
    HistoricalRestartArrangementReceipt,
    HistoricalRestartArrangementWorkflow,
    _arrangement_candidate,
)
from subsystems.orders.service_date_confirmation_workflow import (
    RestartSchedulingAssignmentFacts,
    ServiceDateConfirmationFacts,
    ServiceDateConfirmationReceipt,
    ServiceDateConfirmationWorkflow,
    _candidate,
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

    def replay(self, _key, _fingerprint, *, actor, reason, for_update=False):
        return self.replay_receipt

    def save(self, candidate, **_kwargs):
        self.saved_receipt = ServiceDateConfirmationReceipt(
            candidate.case_no, 1, candidate.order_version,
            candidate.scheduling_version, candidate.service_dates,
            candidate.fingerprint,
        )
        self.replay_receipt = self.saved_receipt
        return self.saved_receipt


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


class _EvidenceOnlyRestartCursor:
    def __init__(self):
        self.statements = []

    def execute(self, statement, parameters):
        self.statements.append((statement, parameters))

    def fetchone(self):
        return {"generation_number": 4}

    def fetchall(self):
        return ({
            "assignment_id": None,
            "staff_id": 12,
            "caregiver_ordinal": 1,
            "staff_name": "王月嫂",
            "service_day_count": 0,
        },)


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


@pytest.mark.parametrize(
    ("actual_start_date", "expected_start"),
    (
        (date(2026, 9, 15), date(2026, 9, 15)),
        (date(2026, 9, 20), date(2026, 9, 20)),
        (date(2026, 9, 25), date(2026, 9, 25)),
        (None, date(2026, 9, 20)),
    ),
)
def test_selectable_dates_use_confirmed_actual_start_as_the_only_available_basis(
    actual_start_date, expected_start
):
    selectable = MySqlServiceDateConfirmationRepository._selectable_dates(
        {
            "start_date": date(2026, 9, 20),
            "actual_start_date": actual_start_date,
            "service_days": 10,
        }
    )

    assert selectable[0] == expected_start
    assert len(selectable) == 40
    assert selectable[-1] == expected_start + timedelta(days=39)


def test_selectable_range_exposes_the_first_ten_consecutive_dates_from_actual_start():
    selectable = MySqlServiceDateConfirmationRepository._selectable_dates(
        {
            "start_date": date(2026, 9, 20),
            "actual_start_date": date(2026, 9, 28),
            "service_days": 10,
        }
    )

    assert selectable[:10] == tuple(
        date(2026, 9, day) if day <= 30 else date(2026, 10, day - 30)
        for day in range(28, 38)
    )


def test_evidence_only_historical_binding_remains_query_evidence():
    cursor = _EvidenceOnlyRestartCursor()
    generation, assignments = MySqlServiceDateConfirmationRepository._restart_scheduling_source(
        cursor, "HIST-EVIDENCE-ONLY", 2
    )
    assert "evidence.assignment_id IS NOT NULL" not in cursor.statements[1][0]
    assert generation == 4
    assert assignments[0].staff_name == "王月嫂"
    assert assignments[0].source_assignment_id is None
    assert assignments[0].staff_id == 12


def test_restart_apply_persists_confirmed_dates_without_schedule():
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

    assert receipt.scheduling_version == 7
    assert repository.commands == []
    assert invalidation.case_nos == ["HIST-70"]
    assert unit.committed is True


def test_restart_apply_replay_keeps_scheduling_version():
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
    assert replay.scheduling_version == 7
    assert repository.commands == []
    assert invalidation.case_nos == ["HIST-71"]


def _pending_arrangement_facts():
    return ServiceDateConfirmationFacts(
        "HIST-ARRANGE", 3, 7, 4, (),
        tuple(date(2026, 9, day) for day in range(6, 13)),
        2,
        (date(2026, 9, 8), date(2026, 9, 9),
         date(2026, 9, 10), date(2026, 9, 11)),
        4,
        (
            RestartSchedulingAssignmentFacts(None, 12, 1, 0, "王月嫂"),
            RestartSchedulingAssignmentFacts(92, 13, 2, 0, "李月嫂"),
        ),
        8.0,
    )


def test_historical_arrangement_requires_explicit_contiguous_multi_staff_ownership():
    facts = _pending_arrangement_facts()
    with pytest.raises(ValueError, match="confirmed_dates_stale"):
        _arrangement_candidate(
            replace(facts, current_confirmed_order_version=2),
            (ArrangementSegmentIntent(12, facts.current_dates[:2]),
             ArrangementSegmentIntent(13, facts.current_dates[2:])),
        )
    with pytest.raises(ValueError, match="staff_allocation_required"):
        _arrangement_candidate(facts, (
            ArrangementSegmentIntent(12, facts.current_dates),
        ))
    with pytest.raises(ValueError, match="date_ownership_mismatch"):
        _arrangement_candidate(facts, (
            ArrangementSegmentIntent(12, (facts.current_dates[0], facts.current_dates[2])),
            ArrangementSegmentIntent(13, (facts.current_dates[1], facts.current_dates[3])),
        ))

    candidate = _arrangement_candidate(facts, (
        ArrangementSegmentIntent(13, facts.current_dates[:2]),
        ArrangementSegmentIntent(12, facts.current_dates[2:]),
    ))
    assert candidate.generation_number == 5
    assert candidate.expected_aggregate_version == 7
    assert [
        (item.staff_id, item.source_assignment_id,
         item.assigned_start_date, item.assigned_end_date,
         item.actual_hours)
        for item in candidate.assignments
    ] == [
        (13, 92, date(2026, 9, 6), date(2026, 9, 9), 16),
        (12, None, date(2026, 9, 10), date(2026, 9, 11), 16),
    ]


def test_historical_arrangement_preview_apply_and_replay_keep_one_generation():
    facts = replace(_pending_arrangement_facts(),
                    restart_assignments=(_pending_arrangement_facts().restart_assignments[0],),
                    contracted_service_days=4)
    segment = ArrangementSegmentIntent(12, facts.current_dates)

    class Repository:
        def __init__(self):
            self.command = None
            self.receipt = None
            self.locked = ()

        def load(self, _case_no, *, lock=False):
            return facts

        def lock_arrangement_staff(self, ids):
            self.locked = ids

        def validate_arrangement_availability(self, candidate, *, lock):
            assert candidate.assignments[0].staff_id == 12

        def arrangement_rate_fingerprint(self, candidate, *, lock):
            return PreviewFingerprint("a" * 64)

        def replay_arrangement(self, key, fingerprint, *, lock):
            return self.receipt

        def persist_arrangement(self, command):
            self.command = command
            self.receipt = HistoricalRestartArrangementReceipt(
                facts.case_no, 8, 5, (101,), command.preview_fingerprint,
            )
            return self.receipt

    repository = Repository()
    unit = _UnitOfWork()
    workflow = HistoricalRestartArrangementWorkflow(repository, lambda: unit)
    preview = workflow.preview(facts.case_no, (segment,))
    kwargs = dict(
        expected_order_version=3,
        expected_scheduling_version=7,
        expected_confirmed_version=2,
        preview_fingerprint=preview.fingerprint.value,
        idempotency_key="hist-arrange-1",
        actor="admin",
        reason="核對既定月嫂與日期",
        correlation_id="hist-arrange-correlation",
    )
    receipt = workflow.apply(facts.case_no, (segment,), **kwargs)
    assert receipt == workflow.apply(facts.case_no, (segment,), **kwargs)
    assert repository.command.command_family == "orders_historical_restart_arrangement"
    assert repository.locked == (12,)
    assert unit.committed


def test_historical_arrangement_carries_source_rate_and_uses_case_policy_only_when_missing():
    class Cursor:
        def execute(self, sql, params):
            self.sql = sql
            self.params = params

        def fetchone(self):
            if "case_staff_assignments" in self.sql:
                return {"case_no": "HIST-RATE", "staff_id": 12}
            return {
                "identity_status": "一般市民",
                "start_date": date(2026, 9, 3),
                "effective_values_json": None,
            }

        def fetchall(self):
            if "assignment_payroll_rate_snapshots" in self.sql:
                return ({
                    "policy_version": "old-v1", "policy_kind": "citizen",
                    "hourly_rate_ntd": 300,
                },)
            return ({
                "policy_version": "current-v2", "policy_kind": "citizen",
                "hourly_rate_ntd": 450,
            },)

    cursor = Cursor()
    facts = (
        type("Assignment", (), {"candidate_key": "a1", "source_assignment_id": 91, "staff_id": 12})(),
        type("Assignment", (), {"candidate_key": "a2", "source_assignment_id": None, "staff_id": 13})(),
    )
    rates = load_historical_restart_arrangement_rates(
        cursor, "HIST-RATE", facts, lock=True,
    )
    assert rates == (
        ("a1", "old-v1", "citizen", 300, "carried-from:91"),
        ("a2", "current-v2", "citizen", 450, "case-policy"),
    )


def test_historical_arrangement_cannot_create_new_assignment_for_retired_staff():
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _sql, _args):
            pass

        def fetchall(self):
            return ({"id": 12, "status": "active", "lifecycle_state": "retired"},)

    class Connection:
        def cursor(self):
            return Cursor()

    with pytest.raises(ValueError, match="staff_ineligible_blocked"):
        MySqlServiceDateConfirmationRepository(Connection()).lock_arrangement_staff((12,))


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
