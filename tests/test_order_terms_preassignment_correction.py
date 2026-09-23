"""
File: test_order_terms_preassignment_correction.py
Description: 驗證未指派案件可補正非排班條款，且排班形狀異動仍維持 fail closed。
"""

from dataclasses import replace
from datetime import date, datetime, time, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.routes.order_terms import OrderTermsApplyBody, OrderTermsInput
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


def test_order_terms_accept_half_hour_precision_and_reject_quarter_hours():
    accepted = OrderTermsInput(
        planned_start_date=date(2026, 9, 10),
        service_days=5,
        service_hours_per_day=4.5,
        requires_cooking=False,
        floor_fee_ntd=0,
        service_time={"start_time": time(9), "end_time": time(13, 30), "end_day_offset": 0},
    )
    assert accepted.to_domain().service_hours_per_day == 4.5

    unknown_cooking = accepted.model_copy(update={"requires_cooking": None})
    assert unknown_cooking.to_domain().requires_cooking is None

    with pytest.raises(ValidationError):
        OrderTermsInput(
            planned_start_date=date(2026, 9, 10),
            service_days=5,
            service_hours_per_day=4.25,
            requires_cooking=False,
            floor_fee_ntd=0,
            service_time={"start_time": time(9), "end_time": time(13, 15), "end_day_offset": 0},
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


class _PreviewReadRepository:
    """Preview deliberately exposes no Terms persistence port."""

    def __init__(self, facts):
        self.facts = facts
        self.reads = 0

    def load_for_preview(self, _case_no):
        self.reads += 1
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


class _NoDownstreamPersistenceRepository(_PersistenceRepository):
    def preflight_impacted_staff_ids(self, _case_no):
        return ()

    def claim_command(self, _request, _command_fingerprint):
        pytest.fail("ordinary Terms save must not claim a permanent command")

    def find_receipt(self, _key, *, for_update):
        pytest.fail("ordinary Terms save must not read a permanent receipt")

    def append_terms_event(self, _request, _preview):
        pytest.fail("ordinary Terms save must not append a Terms event")

    def replace_scheduling_generation(self, _command):
        pytest.fail("ordinary Terms save must not replace Scheduling")

    def persist_lifecycle_impact(self, _command):
        pytest.fail("ordinary Terms save must not persist lifecycle impact")

    def save_receipt(self, _command):
        pytest.fail("ordinary Terms save must not persist a receipt")

    def load_for_apply(self, _case_no, staff_ids):
        assert staff_ids == ()
        return self.facts


class _Clock:
    def now(self):
        return datetime(2026, 8, 23, tzinfo=timezone.utc)


class _UnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class _AssignedPersistenceRepository(_Repository):
    def __init__(self, facts):
        super().__init__(facts)
        self.claimed = False
        self.stored_receipt = None
        self.claims = {}
        self.stored_receipts = {}
        self.pending_order_terms = None
        self.writes = []
        self.payroll_commands = []
        self.receipt_commands = []

    def preflight_impacted_staff_ids(self, _case_no):
        return (3,)

    def claim_command(self, request, command_fingerprint):
        if self.claimed and not self.claims:
            return terms_workflow.CommandClaimState.MATCHED
        key = request.idempotency_key.value
        claimed_fingerprint = self.claims.get(key)
        if claimed_fingerprint is None:
            self.claims[key] = command_fingerprint
            return terms_workflow.CommandClaimState.CREATED
        if claimed_fingerprint == command_fingerprint:
            return terms_workflow.CommandClaimState.MATCHED
        return terms_workflow.CommandClaimState.MISMATCH

    def find_receipt(self, key, *, for_update):
        assert for_update is True
        if self.claims:
            return self.stored_receipts.get(key.value)
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

    def persist_payroll_impact(self, command):
        self.writes.append("payroll")
        self.payroll_commands.append(command)

    def persist_lifecycle_impact(self, _command):
        self.writes.append("lifecycle")
        return 15

    def update_order_terms(self, command):
        self.writes.append("order_terms")
        self.pending_order_terms = command

    def replace_confirmed_service_dates(self, _candidate, _request, _fingerprint):
        self.writes.append("confirmed_service_dates")

    def save_receipt(self, command):
        self.writes.append("receipt")
        self.receipt_commands.append(command)
        self.stored_receipt = command.stored_receipt
        self.stored_receipts[command.key.value] = command.stored_receipt
        if self.pending_order_terms is not None:
            receipt = command.stored_receipt.receipt
            self.facts = replace(
                self.facts,
                order=replace(
                    self.facts.order,
                    terms=self.pending_order_terms.terms,
                    version=receipt.order_version,
                ),
                scheduling=replace(
                    self.facts.scheduling,
                    aggregate_version=receipt.scheduling_version,
                    generation_number=receipt.scheduling_generation,
                ),
                client_finance=replace(
                    self.facts.client_finance,
                    account_version=receipt.client_finance_version,
                ),
                payroll=replace(
                    self.facts.payroll,
                    payroll_version=receipt.payroll_version,
                ),
            )


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


def test_preassignment_non_date_change_preserves_missing_planned_end_date():
    facts = replace(_facts(), planned_end_date=None)
    workflow = terms_workflow.OrderTermsWorkflow(
        _Repository(facts), object(), _Clock()
    )

    proposed = replace(
        _terms(requires_cooking=True), service_hours_per_day=8.0
    )
    preview = workflow.preview("116990823", proposed)

    assert preview.after.requires_cooking is True
    assert preview.planned_end_date is None
    assert len(preview.fingerprint.value) == 64


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


def test_empty_time_terms_allow_independent_change():
    facts = _facts()
    incomplete = replace(
        facts,
        order=replace(
            facts.order,
            terms=_incomplete_terms(requires_cooking=None),
        ),
    )
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(incomplete), object(), _Clock())

    preview = workflow.preview(
        "116990823",
        replace(_incomplete_terms(requires_cooking=True), service_days=4),
    )

    assert preview.after.service_days == 4
    assert preview.after.service_time == incomplete.order.terms.service_time


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
    assert preview.scheduling_replacement_required is False
    assert replacement.scheduling_version == 0
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


def test_preassignment_service_day_count_change_keeps_empty_generation():
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(_facts()), object(), _Clock())

    preview = workflow.preview(
        "116990823", _terms(requires_cooking=False, service_days=4)
    )

    assert preview.scheduling.assignments == ()
    assert preview.scheduling.cancelled_assignment_ids == ()
    assert preview.scheduling.generation_number == 1
    assert preview.after.service_days == 4
    assert preview.planned_end_date == date(2026, 9, 15)


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


def test_preassignment_terms_apply_does_not_require_downstream_roots_or_versions():
    facts = replace(_facts(), client_finance=None, payroll=None)
    repository = _NoDownstreamPersistenceRepository(facts)
    workflow = terms_workflow.OrderTermsWorkflow(repository, object(), _Clock())
    proposed = _terms(requires_cooking=None, start=date(2026, 9, 12))
    preview = workflow.preview("116990823", proposed)
    request = terms_workflow.OrderTermsApplyRequest(
        case_no="116990823",
        proposed_terms=proposed,
        expected_order_version=ExpectedVersion(preview.order_version),
        expected_scheduling_version=ExpectedVersion(preview.scheduling_version),
        expected_client_finance_version=None,
        expected_payroll_version=None,
        preview_fingerprint=preview.fingerprint,
        idempotency_key=None,
        actor=ActorContext("internal-admin"),
        reason=None,
        correlation_id=CorrelationId("terms-no-downstream-roots-correlation"),
        requires_formal_apply=False,
    )

    receipt = workflow.apply_in_current_uow(request)

    assert preview.client_finance_version is None
    assert preview.payroll_version is None
    assert preview.client_finance_impact is None
    assert preview.payroll_impact is None
    assert preview.requires_formal_apply is False
    assert receipt.client_finance_version is None
    assert receipt.payroll_version is None
    assert receipt.scheduling_version == preview.scheduling_version
    assert receipt.scheduling_generation == preview.scheduling_generation
    assert len(repository.saved) == 1
    assert isinstance(repository.saved[0], terms_workflow.OrderTermsPersistenceCommand)
    assert all(
        not isinstance(item, (
            terms_workflow.ClientFinanceImpactPersistenceCommand,
            terms_workflow.PayrollImpactPersistenceCommand,
        ))
        for item in repository.saved
    )


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
    assert preview.scheduling_replacement_required is True
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


def test_assigned_half_hour_terms_keep_fractional_hours_in_finance_and_payroll():
    facts = _assigned_facts()
    repository = _AssignedPersistenceRepository(facts)
    workflow = terms_workflow.OrderTermsWorkflow(repository, object(), _Clock())
    proposed = OrderTerms(
        date(2026, 9, 10),
        5,
        4.5,
        MoneyNTD(0),
        ServiceTimeTerms(time(9), time(13, 30), 0),
        None,
    )

    preview = workflow.preview("116990823", proposed)
    request = terms_workflow.OrderTermsApplyRequest(
        case_no="116990823",
        proposed_terms=proposed,
        expected_order_version=ExpectedVersion(0),
        expected_scheduling_version=ExpectedVersion(2),
        expected_client_finance_version=ExpectedVersion(4),
        expected_payroll_version=ExpectedVersion(7),
        preview_fingerprint=preview.fingerprint,
        idempotency_key=IdempotencyKey("terms-assigned-hours-1"),
        actor=ActorContext("internal-admin"),
        reason="adjust contracted daily hours",
        correlation_id=CorrelationId("terms-assigned-hours-correlation"),
    )

    receipt = workflow.apply_in_current_uow(request)

    assert preview.scheduling.assignments[0].actual_hours == 22.5
    assert preview.scheduling_replacement_required is False
    assert preview.requires_formal_apply is True
    assert preview.client_finance_impact.actions
    assert preview.payroll_impact.actions
    assert preview.payroll_impact.actions[0].amount.amount == 6750
    assert "scheduling_generation" not in repository.writes
    assert repository.payroll_commands[0].assignment_resolution.assignment_id_by_candidate_key == {
        preview.scheduling.assignments[0].candidate_key: 9,
    }
    assert repository.payroll_commands[0].reuse_existing_assignments is True
    assert receipt.scheduling_version == 2
    assert receipt.scheduling_generation == 4
    assert receipt.cancelled_assignment_ids == ()
    assert receipt.created_assignment_keys == ()
    assert repository.receipt_commands[0].scheduling_receipt_id is None


def test_terms_day_replacement_uses_one_target_before_assignment():
    facts = replace(_facts(), confirmed_service_date_version=3,
                    confirmed_service_dates=tuple(date(2026, 9, 10 + n) for n in range(5)))
    proposed = _terms(requires_cooking=False, service_days=3)
    dates = (date(2026, 9, 10), date(2026, 9, 14), date(2026, 9, 16))
    workflow = terms_workflow.OrderTermsWorkflow(_PreviewReadRepository(facts), object(), _Clock())
    preview = workflow.preview(facts.order.case_no, proposed, replacement_service_dates=dates)
    assert preview.after.service_days == 3
    assert preview.confirmed_service_date_candidate.service_dates == dates
    assert preview.confirmed_service_date_candidate.order_version == facts.order.version + 1
    assert preview.scheduling.assignments == ()
    assert preview.planned_end_date == dates[-1]
    assert facts.order.terms.service_days == 5
    assert facts.confirmed_service_date_version == 3


def test_terms_day_replacement_requires_explicit_existing_assignment_allocation():
    facts = _assigned_facts()
    proposed = _terms(requires_cooking=False, service_days=3)
    dates = (date(2026, 9, 10), date(2026, 9, 12), date(2026, 9, 14))
    workflow = terms_workflow.OrderTermsWorkflow(_Repository(facts), object(), _Clock())
    with pytest.raises(ValueError, match="scheduling_reallocation_required"):
        workflow.preview(facts.order.case_no, proposed, replacement_service_dates=dates)
    preview = workflow.preview(facts.order.case_no, proposed,
                              replacement_service_dates=dates,
                              replacement_allocations=((9, 3),))
    assert preview.scheduling.cancelled_assignment_ids == (9,)
    assert preview.scheduling.assignments[0].service_dates == dates
    assert preview.scheduling.assignments[0].source_assignment_id == 9
    assert preview.confirmed_service_date_candidate.service_dates == dates
    assert preview.client_finance_impact.actions
    assert preview.payroll_impact.actions
    assert preview.payroll_impact.actions[0].amount.amount == 3 * 8 * 300


def test_terms_receipt_replay_accepts_half_hour_json_numbers():
    from infrastructure.mysql.order_terms_repository import (
        _optional_integer,
        _required_service_hours,
    )
    assert _required_service_hours({"official_service_hours": 240.0}) == 240.0
    assert _required_service_hours({"official_service_hours": 22.5}) == 22.5
    assert _optional_integer({"version": None}, "version") is None
    assert _optional_integer({"version": 7}, "version") == 7
    for value in (True, -1, 0.25, '240', float('nan')):
        with pytest.raises(ValueError, match='order_terms_receipt_integrity_violation'):
            _required_service_hours({"official_service_hours": value})


def test_apply_http_contract_accepts_absent_downstream_versions():
    body = OrderTermsApplyBody.model_validate({
        "proposed_terms": _terms(requires_cooking=None).canonical_payload(),
        "expected_order_version": 0,
        "expected_scheduling_version": 0,
        "expected_client_finance_version": None,
        "expected_payroll_version": None,
        "preview_fingerprint": "a" * 64,
        "requires_formal_apply": False,
    })

    assert body.expected_client_finance_version is None
    assert body.expected_payroll_version is None
    assert body.reason is None
    assert body.requires_formal_apply is False


@pytest.mark.parametrize('dates,allocation,error', [
    ((date(2026, 9, 10),), ((9, 3),), 'service date count'),
    ((date(2026, 9, 10),) * 3, ((9, 3),), 'unique and sorted'),
    ((date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)), ((9, 3),), 'outside_selectable_range'),
    ((date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 15)), ((9, 3),), 'outside_selectable_range'),
    ((date(2026, 9, 10), date(2026, 9, 12), date(2026, 9, 14)), ((999, 3),), 'scheduling_reallocation_required'),
])
def test_invalid_replacement_is_rejected_without_writes(dates, allocation, error):
    repository = _AssignedPersistenceRepository(_assigned_facts())
    workflow = terms_workflow.OrderTermsWorkflow(repository, object(), _Clock())
    with pytest.raises(ValueError, match=error):
        workflow.preview('116990823', _terms(requires_cooking=False, service_days=3),
                         replacement_service_dates=dates, replacement_allocations=allocation)
    assert repository.writes == []


def test_replacement_rejects_stale_confirmed_date_version_and_started_service():
    facts = _assigned_facts()
    repository = _AssignedPersistenceRepository(facts)
    workflow = terms_workflow.OrderTermsWorkflow(repository, object(), _Clock())
    proposed = _terms(requires_cooking=False, service_days=3)
    dates = (date(2026, 9, 10), date(2026, 9, 12), date(2026, 9, 14))
    preview = workflow.preview(facts.order.case_no, proposed,
                               replacement_service_dates=dates, replacement_allocations=((9, 3),))
    request = terms_workflow.OrderTermsApplyRequest(facts.order.case_no, proposed,
        ExpectedVersion(preview.order_version), ExpectedVersion(preview.scheduling_version),
        ExpectedVersion(preview.client_finance_version), ExpectedVersion(preview.payroll_version),
        preview.fingerprint, IdempotencyKey('issue326-stale'), ActorContext('synthetic'),
        'synthetic replacement', CorrelationId('issue326'), dates, ((9, 3),))
    repository.facts = replace(facts, confirmed_service_date_version=4)
    with pytest.raises(terms_workflow.TermsWorkflowError) as caught:
        workflow.apply_in_current_uow(request)
    assert caught.value.error.code == 'stale_preview'
    assert repository.writes == []
    repository.facts = replace(facts, scheduling=replace(facts.scheduling, service_started=True))
    with pytest.raises(ValueError, match='service_started_replacement_blocked'):
        workflow.preview(facts.order.case_no, proposed,
                         replacement_service_dates=dates, replacement_allocations=((9, 3),))
    assert repository.writes == []
