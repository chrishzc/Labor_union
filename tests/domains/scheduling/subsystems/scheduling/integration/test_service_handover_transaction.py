"""Real handover/Payroll planning with an atomic in-memory persistence boundary."""

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.assignment_plan import AssignmentPlanFacts, EffectiveAssignmentFact
from domains.scheduling.leave_substitution import LeaveResolutionType, LeaveSubstitutionBatchIntent, LeaveSubstitutionItem, OfficialScheduleFact
from infrastructure.mysql.leave_substitution_repository import _request_snapshot as repository_snapshot
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.errors import ErrorCategory
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.payroll.terms_impact import ExistingStaffObligationTermsFact, PayrollTermsSourceFacts, SourceAssignmentPayrollTerms, StaffObligationKind, StaffObligationDirection, build_payroll_handover_impact
from subsystems.scheduling.assignment_plan_impacts import AssignmentPlanDomainImpact
from subsystems.scheduling.holiday_calendar_query import HolidayCalendarFacts
from subsystems.scheduling.leave_substitution_workflow import (
    CommandClaimState, LeaveApplyEvidence, LeaveBatchHeaderEvidence, LeaveOutcomeEvidence,
    LeaveSubstitutionApplyRequest, LeaveSubstitutionPreviewRequest, LeaveSubstitutionWorkflow,
    LeaveSubstitutionWorkflowError, LeaveSubstitutionWorkflowFacts, _request_snapshot,
)

TODAY = date(2026, 10, 21)
DAYS = tuple(TODAY + timedelta(days=offset) for offset in range(-2, 6))
INTENT = LeaveSubstitutionBatchIntent(1, tuple(LeaveSubstitutionItem(index + 10, day,
    LeaveResolutionType.SUBSTITUTE, 8) for index, day in enumerate(DAYS) if day >= TODAY), TODAY)


def source_facts(paid=2000):
    plan = AssignmentPlanFacts("HANDOVER", 1, 1, 1, 1, 1, 8, 8, True,
        (EffectiveAssignmentFact(1, 7, 1, DAYS[0], DAYS[-1], DAYS),))
    payroll = PayrollTermsSourceFacts("HANDOVER", 1,
        (SourceAssignmentPayrollTerms(1, 7, "policy-v1", PayrollPolicyKind.CITIZEN),),
        (ExistingStaffObligationTermsFact("original", 1, 7, StaffObligationKind.SERVICE_PAY,
            StaffObligationDirection.PAYABLE_TO_STAFF, MoneyNTD(20200), MoneyNTD(20200 - paid), MoneyNTD(paid), True, date(2026, 11, 30)),),
        date(2026, 11, 30))
    owners = SimpleNamespace(assignment_plan=plan, lifecycle=SimpleNamespace(service_data_locked=False),
        payroll=payroll, order_terms=OrderTerms(DAYS[0], 8, 8, MoneyNTD(1000), ServiceTimeTerms(None, None, None)),
        client_finance=SimpleNamespace(existing_obligations=(SimpleNamespace(contracted_amount=MoneyNTD(25000), net_settled_amount=MoneyNTD(25000)),)))
    return LeaveSubstitutionWorkflowFacts(owners, tuple(OfficialScheduleFact(index + 10, 1, 7, day) for index, day in enumerate(DAYS)))


class Repository:
    def __init__(self):
        self.facts = source_facts()
        self.state = {}
        self.fresh_reads = 0

    def load_for_preview(self, *_args):
        return self.facts

    def preflight_impacted_staff_ids(self, *_args):
        return (7, 8)

    def load_replay_evidence(self, request, command_fingerprint):
        stored = self.state.get("receipt")
        if stored is None:
            return None
        claim = CommandClaimState.MATCHED if stored.command_fingerprint == command_fingerprint else CommandClaimState.MISMATCH
        return LeaveApplyEvidence(None, claim, self.state["header"], self.state["outcomes"], stored)

    def load_for_apply(self, request, _staff_ids, _fingerprint, after_command_lock):
        self.fresh_reads += 1
        self.state["claim"] = request.idempotency_key.value
        return LeaveApplyEvidence(self.facts, CommandClaimState.CREATED, None, (), None), after_command_lock(7)

    def replace_scheduling_generation(self, candidate, context):
        self.state["generation"] = candidate
        assert context.handover_date == TODAY
        return SimpleNamespace(generation_id=2)

    def append_batch_outcomes(self, request, preview, command_fingerprint, _result):
        snapshot = repository_snapshot(request)
        self.state["header"] = LeaveBatchHeaderEvidence(request.idempotency_key.value, request.case_no,
            command_fingerprint, preview.fingerprint, len(request.intent.items), request.actor.actor_id, request.reason,
            fingerprint_payload(snapshot), snapshot)
        self.state["outcomes"] = tuple(LeaveOutcomeEvidence(index + 100, index, request.intent.original_assignment_id,
            item.original_schedule_id, item.work_date.isoformat(), item.resolution_type.value,
            fingerprint_payload({"item": index})) for index, item in enumerate(request.intent.items))
        return tuple(item.outcome_event_id for item in self.state["outcomes"])

    def save_receipt(self, stored, *_args):
        self.state["receipt"] = stored


class UnitOfWork:
    def __init__(self, repository):
        self.repository = repository
        self.commits = 0

    def __enter__(self):
        self.before = deepcopy(self.repository.state)
        self.committed = False
        return self

    def commit(self):
        self.committed = True
        self.commits += 1

    def __exit__(self, *_args):
        if not self.committed:
            self.repository.state = self.before


class FinancePort:
    def __init__(self, repository):
        self.repository = repository

    def preview_leave_substitution(self, *_args):
        return AssignmentPlanDomainImpact(1, 2, fingerprint_payload({"client": 25000}), (),
            SimpleNamespace(stage_plans=(SimpleNamespace(amount=MoneyNTD(25000)),)))

    def persist_leave_substitution(self, candidate, *_args):
        self.repository.state["client"] = candidate


class PayrollPort:
    def __init__(self, repository, fail=False):
        self.repository = repository
        self.fail = fail

    def preview_handover(self, facts, scheduling):
        candidate = build_payroll_handover_impact(facts.payroll, scheduling, facts.order_terms, "handover-1")
        return AssignmentPlanDomainImpact(1, 2, candidate.fingerprint, (), candidate)

    def persist_leave_substitution(self, candidate, *_args):
        self.repository.state["payroll"] = candidate
        self.repository.state["payables"] = candidate.payload.frozen_settlements
        self.repository.state["outbox"] = "staff_obligation_changed"
        if self.fail:
            raise ValueError("staff_payables_correction_stale")


class OrdersPort(FinancePort):
    def preview_leave_substitution(self, *_args):
        return AssignmentPlanDomainImpact(1, 2, fingerprint_payload({"orders": 2}), (), None)

    def persist_leave_substitution(self, candidate, *_args):
        self.repository.state["orders"] = candidate


def workflow(*, fail=False):
    repository = Repository()
    uow = UnitOfWork(repository)
    clock = FixedBusinessClock(datetime(2026, 10, 21, 10, tzinfo=TAIPEI_TIME_ZONE))
    holiday_query = SimpleNamespace(query=lambda *_args, **_kwargs: HolidayCalendarFacts("test-calendar", "holidays-v1", ()))
    application = LeaveSubstitutionWorkflow(repository, FinancePort(repository), PayrollPort(repository, fail),
        OrdersPort(repository), holiday_query, lambda: uow, clock=clock)
    return application, repository, uow


def command(preview):
    return LeaveSubstitutionApplyRequest("HANDOVER", INTENT, ExpectedVersion(1), ExpectedVersion(1),
        ExpectedVersion(1), ExpectedVersion(1), preview.fingerprint, IdempotencyKey("handover-1"),
        ActorContext("operator"), "", CorrelationId("handover-1"))


def test_preview_is_zero_write_and_apply_commits_all_owners_once_then_replays_before_clock_or_source_reads():
    application, repository, uow = workflow()
    preview = application.preview(LeaveSubstitutionPreviewRequest("HANDOVER", INTENT, CorrelationId("preview")))
    assert repository.state == {}
    assert preview.accounting.client.difference_ntd == 0
    assert preview.calendar_candidate.leave_day_count == 0
    request = command(preview)
    receipt = application.apply(request)
    assert uow.commits == 1
    assert set(repository.state) == {"claim", "generation", "header", "outcomes", "client", "payroll", "payables", "outbox", "orders", "receipt"}
    before = deepcopy(repository.state)
    application._clock = FixedBusinessClock(datetime(2026, 10, 22, 10, tzinfo=TAIPEI_TIME_ZONE))
    assert application.apply(request) == receipt
    assert repository.fresh_reads == 1
    assert repository.state == before
    assert repository_snapshot(request) == _request_snapshot(request)
    assert repository_snapshot(request)["handover_date"] == TODAY.isoformat()


def test_payables_failure_rolls_back_schedule_finance_payroll_outbox_and_receipt_together():
    application, repository, uow = workflow(fail=True)
    preview = application.preview(LeaveSubstitutionPreviewRequest("HANDOVER", INTENT, CorrelationId("preview")))
    with pytest.raises(LeaveSubstitutionWorkflowError) as caught:
        application.apply(command(preview))
    assert caught.value.error.category is ErrorCategory.CONFLICT
    assert repository.state == {}
    assert uow.commits == 0


def test_new_payout_between_query_and_apply_is_a_typed_stale_conflict_even_without_payroll_version_change():
    application, repository, uow = workflow()
    preview = application.preview(LeaveSubstitutionPreviewRequest("HANDOVER", INTENT, CorrelationId("preview")))
    fresh = source_facts(paid=3000)
    repository.facts = fresh
    with pytest.raises(LeaveSubstitutionWorkflowError) as caught:
        application.apply(command(preview))
    assert caught.value.error.code == "stale_preview"
    assert repository.state == {}
    assert uow.commits == 0


def test_same_key_cannot_change_reason_or_handover_intent_after_commit():
    application, repository, uow = workflow()
    request = command(application.preview(LeaveSubstitutionPreviewRequest("HANDOVER", INTENT, CorrelationId("preview"))))
    application.apply(request)
    before = deepcopy(repository.state)
    with pytest.raises(LeaveSubstitutionWorkflowError) as caught:
        application.apply(replace(request, reason="different"))
    assert caught.value.error.category is ErrorCategory.IDEMPOTENCY_MISMATCH
    assert repository.state == before
    assert uow.commits == 1


def test_http_handover_contract_exposes_owner_money_and_preserves_typed_intent():
    from api.routes.leave_substitution import _preview_payload
    from api.schemas.leave_substitution import LeaveSubstitutionPreviewBody, LeaveSubstitutionPreviewView

    application, _, _ = workflow()
    preview = application.preview(LeaveSubstitutionPreviewRequest("HANDOVER", INTENT, CorrelationId("preview")))
    view = LeaveSubstitutionPreviewView.model_validate(_preview_payload(preview))
    assert view.accounting.client.difference_ntd == 0
    original = next(item for item in view.accounting.staff if item.staff_id == 7)
    assert original.after.total_ntd == 5050
    assert original.paid_net_ntd == 2000
    assert original.payable_after_ntd == 3050
    assert original.payment_due_date == date(2026, 11, 30)
    payload = {"original_assignment_id": 1, "handover_date": TODAY.isoformat(), "items": [
        {"original_schedule_id": item.original_schedule_id, "work_date": item.work_date.isoformat(),
         "resolution_type": "substitute", "substitute_staff_id": 8} for item in INTENT.items]}
    assert LeaveSubstitutionPreviewBody.model_validate(payload).to_intent() == INTENT


def test_staff_only_handover_preserves_exactly_settled_client_obligations_without_refund_or_extra_charge():
    from domains.client_finance.obligation_planning import (ClientFinanceTermsSourceFacts, ClientObligationActionKind,
        ClientPaymentTerms, ExistingClientStageObligation, build_client_finance_terms_impact)
    from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
    from domains.scheduling.leave_substitution import build_leave_substitution_candidate

    facts = source_facts()
    before_generation = SchedulingGenerationCandidate("HANDOVER", 1, 1, 2, (), (
        AssignmentCandidate("before", 1, 7, 1, DAYS[0], DAYS[-1], DAYS, 64),), ())
    finance = ClientFinanceTermsSourceFacts("HANDOVER", 1,
        ClientPaymentTerms(2, MoneyNTD(350), DAYS[0] - timedelta(days=2), DAYS[0], None), (), ())
    initial = build_client_finance_terms_impact(finance, facts.impact_facts.order_terms, before_generation, "initial")
    settled = replace(finance, existing_obligations=tuple(ExistingClientStageObligation(
        f"client:{plan.payment_stage.value}", plan.payment_stage, plan.amount, plan.amount, plan.due_date,
        plan.amount.amount > 0) for plan in initial.stage_plans))
    after_generation = build_leave_substitution_candidate(replace(facts.leave_facts, business_date=TODAY), INTENT).scheduling
    after = build_client_finance_terms_impact(settled, facts.impact_facts.order_terms, after_generation, "handover")
    assert after.blockers == ()
    assert all(action.action is ClientObligationActionKind.UNCHANGED for action in after.actions)
    assert sum(plan.amount.amount for plan in after.stage_plans) == sum(plan.amount.amount for plan in initial.stage_plans)


def test_inconsistent_official_double_pay_and_payroll_facts_block_handover_without_guessing_money():
    application, repository, uow = workflow()
    repository.facts = replace(repository.facts, official_schedules=tuple(
        replace(row, is_double_pay=True) if row.work_date == DAYS[0] else row
        for row in repository.facts.official_schedules))
    preview = application.preview(LeaveSubstitutionPreviewRequest("HANDOVER", INTENT, CorrelationId("preview")))
    assert preview.apply_readiness.blockers == ("payroll_special_pay_lineage_mismatch",)
    assert preview.accounting is None
    with pytest.raises(LeaveSubstitutionWorkflowError):
        application.apply(command(preview))
    assert repository.state == {}
    assert uow.commits == 0


def test_handover_cannot_resolve_linked_temporary_leave_or_enqueue_its_notification():
    from pydantic import ValidationError
    from api.schemas.leave_substitution import LeaveSubstitutionPreviewBody
    from subsystems.scheduling.leave_substitution_workflow import LinkedLeaveRequestIntent

    with pytest.raises(ValidationError, match="handover_linked_leave_not_supported"):
        LeaveSubstitutionPreviewBody.model_validate({"original_assignment_id": 1, "handover_date": TODAY,
            "leave_request_id": 77, "expected_leave_request_version": 1})
    with pytest.raises(ValueError, match="handover_linked_leave_not_supported"):
        LeaveSubstitutionPreviewRequest("HANDOVER", INTENT, CorrelationId("preview"), LinkedLeaveRequestIntent(77, 1))
