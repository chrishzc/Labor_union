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
from domains.scheduling.generation import SchedulingGenerationFacts
from shared_kernel.money import MoneyNTD
from subsystems.orders import terms_workflow
from subsystems.payroll.terms_impact import PayrollTermsSourceFacts
from subsystems.payroll.terms_impact import (
    ExistingStaffObligationTermsFact,
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

    def save_receipt(self, command):
        self.saved.append(command)


class _Clock:
    def now(self):
        return datetime(2026, 8, 23, tzinfo=timezone.utc)


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


@pytest.mark.parametrize(
    "proposed",
    (
        _terms(requires_cooking=False, start=date(2026, 9, 11)),
        _terms(requires_cooking=False, service_days=4),
    ),
)
def test_preassignment_schedule_shape_change_still_requires_segments(proposed):
    with pytest.raises(ValueError, match="scheduling_segments_required"):
        terms_workflow._scheduling_candidate(_facts(), proposed)


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


def test_empty_impacted_staff_set_requires_no_mutex_query():
    cursor = SimpleNamespace(execute=lambda *_args: pytest.fail("unexpected SQL"))

    from infrastructure.mysql.order_terms_read_model import lock_staff_mutexes

    lock_staff_mutexes(cursor, ())


def test_terms_rebuild_accepts_empty_assignment_resolution():
    from infrastructure.mysql.scheduling_replacement_writer import (
        _assignment_resolution,
    )

    resolution = _assignment_resolution(
        SimpleNamespace(command_family="orders_terms_rebuild"),
        {},
    )

    assert dict(resolution.assignment_id_by_candidate_key) == {}
