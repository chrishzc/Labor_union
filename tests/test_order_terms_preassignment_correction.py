"""
File: test_order_terms_preassignment_correction.py
Description: 驗證未指派案件可補正非排班條款，且排班形狀異動仍維持 fail closed。
"""

from dataclasses import replace
from datetime import date, datetime, time, timezone
from types import SimpleNamespace

import pytest

from domains.client_finance.obligation_planning import (
    ClientFinanceTermsSourceFacts,
    ClientPaymentTerms,
)
from domains.orders.lifecycle import OrderLifecycleRootFacts, OrderLifecycleStatus
from domains.orders.terms import OrderAggregateFacts, OrderTerms, ServiceTimeTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import (
    EffectiveAssignmentSegment,
    SchedulingGenerationFacts,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.orders import terms_workflow
from subsystems.payroll.terms_impact import (
    ExistingStaffObligationTermsFact,
    PayrollTermsSourceFacts,
    SourceAssignmentPayrollTerms,
    StaffObligationDirection,
    StaffObligationKind,
)


def _terms(*, requires_cooking, start=date(2026, 9, 10), service_days=5):
    return OrderTerms(
        start,
        service_days,
        8,
        MoneyNTD(0),
        ServiceTimeTerms(time(9), time(17), 0),
        requires_cooking,
    )


def _incomplete_terms(*, requires_cooking):
    return OrderTerms(
        date(2026, 9, 10),
        5,
        8,
        MoneyNTD(0),
        ServiceTimeTerms(None, None, None),
        requires_cooking,
    )


def _facts():
    current = _terms(requires_cooking=None)
    return terms_workflow.TermsWorkflowFacts(
        order=OrderAggregateFacts("116990823", 0, current, False, "一般市民"),
        scheduling=SchedulingGenerationFacts("116990823", 0, 0, ()),
        planned_service_dates=(),
        planned_end_date=date(2026, 9, 16),
        client_finance=ClientFinanceTermsSourceFacts(
            "116990823",
            4,
            ClientPaymentTerms(
                2,
                MoneyNTD(350),
                date(2026, 8, 30),
                date(2026, 9, 30),
                None,
            ),
            (),
            (),
        ),
        payroll=PayrollTermsSourceFacts("116990823", 7, (), (), None),
        lifecycle=OrderLifecycleRootFacts(
            "116990823",
            OrderLifecycleStatus.DISCUSSION,
            False,
            None,
            False,
            False,
            False,
        ),
    )


class _Repository:
    def __init__(self, facts):
        self.facts = facts

    def load_for_preview(self, _case_no):
        return self.facts


class _PersistenceRepository(_Repository):
    def __init__(self, facts):
        super().__init__(facts)
        self.saved = []

    def append_terms_event(self, _request, _preview):
        return 11

    def replace_scheduling_generation(self, _command):
        return terms_workflow.SchedulingReplacementResult(
            12, 1, 13, 14, SimpleNamespace(assignment_id_by_candidate_key={})
        )

    def persist_client_finance_impact(self, _command):
        pytest.fail("client finance writer must be skipped")

    def persist_payroll_impact(self, _command):
        pytest.fail("payroll writer must be skipped")

    def persist_lifecycle_impact(self, _command):
        return 15

    def update_order_terms(self, command):
        self.saved.append(command)

    def replace_confirmed_service_dates(self, candidate, _request, _fingerprint):
        self.saved.append(candidate)

    def save_receipt(self, command):
        self.saved.append(command)


class _Clock:
    def now(self):
        return datetime(2026, 8, 23, tzinfo=timezone.utc)


class _AssignedPersistenceRepository(_Repository):
    def __init__(self, facts):
        super().__init__(facts)
        self.claimed = False
        self.stored_receipt = None
        self.writes = []

    def preflight_impacted_staff_ids(self, _case_no):
        return (3,)

    def claim_command(self, _request, _command_fingerprint):
        if self.claimed:
            return terms_workflow.CommandClaimState.MATCHED
        self.claimed = True
        return terms_workflow.CommandClaimState.CREATED

    def find_receipt(self, _key, *, for_update):
        assert for_update is True
        return self.stored_receipt

    def load_for_apply(self, _case_no, staff_ids):
        assert staff_ids == (3,)
        return self.facts

    def append_terms_event(self, _request, _preview):
        self.writes.append("terms_event")
        return 11

    def replace_scheduling_generation(self, command):
        self.writes.append("scheduling_generation")
        candidate_key = command.candidate.assignments[0].candidate_key
        return terms_workflow.SchedulingReplacementResult(
            12,
            command.candidate.resulting_aggregate_version,
            13,
            14,
            SimpleNamespace(assignment_id_by_candidate_key={candidate_key: 21}),
        )

    def persist_client_finance_impact(self, _command):
        self.writes.append("client_finance")

    def persist_payroll_impact(self, _command):
        self.writes.append("payroll")

    def persist_lifecycle_impact(self, _command):
        self.writes.append("lifecycle")
        return 15

    def update_order_terms(self, _command):
        self.writes.append("order_terms")

    def replace_confirmed_service_dates(self, _candidate, _request, _fingerprint):
        self.writes.append("confirmed_service_dates")

    def save_receipt(self, command):
        self.writes.append("receipt")
        self.stored_receipt = command.stored_receipt


def _assigned_facts():
    service_dates = tuple(date(2026, 9, 10 + offset) for offset in range(5))
    return replace(
        _facts(),
        scheduling=SchedulingGenerationFacts(
            "116990823",
            2,
            4,
            (
                EffectiveAssignmentSegment(
                    9,
                    3,
                    1,
                    5,
                    service_dates[0],
                    service_dates[-1],
                    service_dates,
                ),
            ),
        ),
        planned_service_dates=service_dates,
        confirmed_service_date_version=3,
        confirmed_service_dates=service_dates,
        payroll=PayrollTermsSourceFacts(
            "116990823",
            7,
            (
                SourceAssignmentPayrollTerms(
                    9,
                    3,
                    "citizen-v1",
                    PayrollPolicyKind.CITIZEN,
                ),
            ),
            (),
            date(2026, 10, 5),
        ),
    )


def test_preassignment_cooking_correction_builds_empty_scheduling_candidate(
):
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(_facts()), object(), _Clock())

    preview = workflow.preview("116990823", _terms(requires_cooking=False))

    assert preview.after.requires_cooking is False
    assert preview.scheduling.assignments == ()
    assert preview.scheduling.cancelled_assignment_ids == ()
    assert preview.planned_end_date == date(2026, 9, 16)
    assert preview.lifecycle_impact.actual_end_date is None
    assert preview.client_finance_impact.resulting_account_version == 4
    assert preview.payroll_impact.resulting_payroll_version == 7
    assert preview.client_finance_impact.actions == ()
    assert preview.payroll_impact.actions == ()


def test_incomplete_time_terms_allow_only_unique_cooking_correction():
    facts = _facts()
    incomplete = replace(
        facts,
        order=replace(
            facts.order,
            terms=_incomplete_terms(requires_cooking=None),
        ),
    )
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(incomplete), object(), _Clock())

    preview = workflow.preview("116990823", _incomplete_terms(requires_cooking=True))

    assert preview.after.requires_cooking is True
    assert preview.scheduling.assignments == ()


def test_incomplete_time_terms_reject_non_cooking_change():
    facts = _facts()
    incomplete = replace(
        facts,
        order=replace(
            facts.order,
            terms=_incomplete_terms(requires_cooking=None),
        ),
    )
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(incomplete), object(), _Clock())

    with pytest.raises(ValueError, match="service_time_terms_incomplete"):
        workflow.preview(
            "116990823",
            replace(_incomplete_terms(requires_cooking=True), service_days=4),
        )


def test_preassignment_persist_skips_finance_and_payroll_writers():
    repository = _PersistenceRepository(_facts())
    workflow = terms_workflow.OrderTermsWorkflow(repository, object(), _Clock())
    preview = workflow.preview("116990823", _terms(requires_cooking=False))
    request = SimpleNamespace(
        case_no="116990823",
        proposed_terms=_terms(requires_cooking=False),
        idempotency_key="terms-noop-1",
        actor="internal-admin",
        reason="complete imported cooking requirement",
        correlation_id="terms-noop-correlation",
    )

    workflow._persist(
        request,
        preview,
        preview.fingerprint,
        terms_workflow._build_receipt(preview),
    )

    assert len(repository.saved) == 2


def test_preassignment_start_date_shift_replaces_confirmed_service_dates():
    facts = replace(
        _facts(),
        confirmed_service_date_version=3,
        confirmed_service_dates=tuple(
            date(2026, 9, 10 + offset) for offset in range(5)
        ),
    )
    repository = _PersistenceRepository(facts)
    workflow = terms_workflow.OrderTermsWorkflow(repository, object(), _Clock())
    preview = workflow.preview(
        "116990823",
        _terms(requires_cooking=None, start=date(2026, 9, 13)),
    )
    request = SimpleNamespace(
        case_no="116990823",
        proposed_terms=preview.after,
        idempotency_key="terms-date-shift-1",
        actor="internal-admin",
        reason="move planned service period",
        correlation_id="terms-date-shift-correlation",
    )

    workflow._persist(
        request,
        preview,
        preview.fingerprint,
        terms_workflow._build_receipt(preview),
    )

    replacement = next(
        item
        for item in repository.saved
        if isinstance(item, terms_workflow.ConfirmedServiceDateCandidate)
    )
    assert replacement.order_version == 1
    assert replacement.scheduling_version == 1
    assert replacement.service_dates == tuple(
        date(2026, 9, 13 + offset) for offset in range(5)
    )


def test_order_terms_date_replacement_invalidates_matching_confirmation(monkeypatch):
    from infrastructure.mysql import matching_schedule_confirmation_repository
    from infrastructure.mysql import service_date_confirmation_repository
    from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository

    calls = []

    class _ServiceDates:
        def __init__(self, connection):
            assert connection is sentinel

        def save(self, candidate, **evidence):
            calls.append(("service_dates", candidate.case_no, evidence))

    class _MatchingConfirmation:
        def __init__(self, connection):
            assert connection is sentinel

        def invalidate_current_snapshot(self, case_no):
            calls.append(("matching_confirmation", case_no))

    sentinel = object()
    monkeypatch.setattr(
        service_date_confirmation_repository,
        "MySqlServiceDateConfirmationRepository",
        _ServiceDates,
    )
    monkeypatch.setattr(
        matching_schedule_confirmation_repository,
        "MySqlMatchingScheduleConfirmationRepository",
        _MatchingConfirmation,
    )
    request = SimpleNamespace(
        actor=ActorContext("internal-admin"),
        reason="move assigned service period",
        idempotency_key=IdempotencyKey("terms-matching-invalidation-1"),
    )

    MySqlOrderTermsRepository(sentinel).replace_confirmed_service_dates(
        SimpleNamespace(case_no="116990823"),
        request,
        terms_workflow.fingerprint_payload({"case_no": "116990823"}),
    )

    assert calls[0][0:2] == ("service_dates", "116990823")
    assert calls[1] == ("matching_confirmation", "116990823")


def test_preassignment_finance_obligation_fails_closed():
    facts = _facts()
    invalid = replace(
        facts,
        client_finance=replace(
            facts.client_finance, open_nonstage_obligation_count=1
        ),
    )
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(invalid), object(), _Clock())

    with pytest.raises(
        ValueError, match="preassignment_client_finance_obligation_conflict"
    ):
        workflow.preview("116990823", _terms(requires_cooking=False))


def test_preassignment_payroll_obligation_fails_closed():
    facts = _facts()
    obligation = ExistingStaffObligationTermsFact(
        "staff-obligation:legacy",
        9,
        3,
        StaffObligationKind.SERVICE_PAY,
        StaffObligationDirection.PAYABLE_TO_STAFF,
        MoneyNTD(100),
        MoneyNTD(100),
        MoneyNTD(0),
        False,
        None,
    )
    invalid = replace(
        facts,
        payroll=replace(facts.payroll, existing_obligations=(obligation,)),
    )
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(invalid), object(), _Clock())

    with pytest.raises(
        ValueError, match="preassignment_payroll_obligation_conflict"
    ):
        workflow.preview("116990823", _terms(requires_cooking=False))


def test_preassignment_service_day_count_change_still_requires_segments():
    with pytest.raises(ValueError, match="scheduling_segments_required"):
        terms_workflow._scheduling_candidate(
            _facts(), _terms(requires_cooking=False, service_days=4)
        )


def test_preassignment_start_date_shift_keeps_empty_generation_and_shifts_end_date():
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(_facts()), object(), _Clock())

    preview = workflow.preview(
        "116990823",
        _terms(requires_cooking=False, start=date(2026, 9, 13)),
    )

    assert preview.scheduling.assignments == ()
    assert preview.scheduling.cancelled_assignment_ids == ()
    assert preview.after.planned_start_date == date(2026, 9, 13)
    assert preview.planned_end_date == date(2026, 9, 19)


def test_preassignment_service_started_fails_closed():
    facts = _facts()
    invalid = replace(
        facts,
        scheduling=replace(facts.scheduling, service_started=True),
    )

    with pytest.raises(ValueError, match="preassignment_service_started_conflict"):
        terms_workflow._scheduling_candidate(
            invalid, _terms(requires_cooking=False, service_days=4)
        )


def test_preassignment_service_started_allows_unique_cooking_correction():
    facts = _facts()
    started = replace(
        facts,
        scheduling=replace(facts.scheduling, service_started=True),
    )
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(started), object(), _Clock())

    preview = workflow.preview("116990823", _terms(requires_cooking=False))

    assert preview.after.requires_cooking is False
    assert preview.scheduling.assignments == ()
    assert preview.scheduling.cancelled_assignment_ids == ()


def test_service_data_lock_rejects_unique_cooking_correction():
    facts = _facts()
    locked = replace(
        facts,
        order=replace(facts.order, service_data_locked=True),
    )
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(locked), object(), _Clock())

    with pytest.raises(ValueError, match="service_data_locked"):
        workflow.preview("116990823", _terms(requires_cooking=True))


def test_assigned_start_date_shift_rebuilds_owned_impacts_and_replays_receipt():
    facts = _assigned_facts()
    repository = _AssignedPersistenceRepository(facts)
    workflow = terms_workflow.OrderTermsWorkflow(repository, object(), _Clock())
    proposed = _terms(requires_cooking=None, start=date(2026, 9, 13))
    preview = workflow.preview("116990823", proposed)
    request = terms_workflow.OrderTermsApplyRequest(
        case_no="116990823",
        proposed_terms=proposed,
        expected_order_version=ExpectedVersion(0),
        expected_scheduling_version=ExpectedVersion(2),
        expected_client_finance_version=ExpectedVersion(4),
        expected_payroll_version=ExpectedVersion(7),
        preview_fingerprint=preview.fingerprint,
        idempotency_key=IdempotencyKey("terms-assigned-date-shift-1"),
        actor=ActorContext("internal-admin"),
        reason="move assigned service period",
        correlation_id=CorrelationId("terms-assigned-date-shift-correlation"),
    )

    receipt = workflow.apply_in_current_uow(request)
    write_count = len(repository.writes)
    replayed = workflow.apply_in_current_uow(request)

    assignment = preview.scheduling.assignments[0]
    assert preview.scheduling.generation_number == 5
    assert preview.scheduling.cancelled_assignment_ids == (9,)
    assert assignment.source_assignment_id == 9
    assert assignment.assigned_start_date == date(2026, 9, 13)
    assert assignment.assigned_end_date == date(2026, 9, 17)
    assert assignment.service_dates == tuple(
        date(2026, 9, 13 + offset) for offset in range(5)
    )
    assert preview.client_finance_impact.resulting_account_version == 5
    assert preview.client_finance_impact.actions
    assert preview.payroll_impact.resulting_payroll_version == 8
    assert preview.payroll_impact.actions
    assert preview.lifecycle_impact.actual_end_date == date(2026, 9, 17)
    assert preview.confirmed_service_date_candidate is not None
    assert preview.confirmed_service_date_candidate.service_dates == assignment.service_dates
    assert repository.writes == [
        "terms_event",
        "scheduling_generation",
        "client_finance",
        "payroll",
        "lifecycle",
        "order_terms",
        "confirmed_service_dates",
        "receipt",
    ]
    assert replayed == receipt
    assert len(repository.writes) == write_count
