from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import SimpleNamespace

import pytest

from domains.client_finance.obligation_planning import (
    ClientFinanceTermsSourceFacts,
    ClientPaymentTerms,
)
from domains.orders.actual_start import (
    ActualStartCandidateError,
    ActualStartReconfirmationFacts,
    ActualStartReconfirmationState,
)
from domains.orders.historical_adoption import (
    HistoricalOrderCurrentFacts,
    HistoricalOrderSourceStatus,
)
from domains.orders.lifecycle import OrderLifecycleRootFacts, OrderLifecycleStatus
from domains.orders.terms import OrderAggregateFacts, OrderTerms, ServiceTimeTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import (
    EffectiveAssignmentSegment,
    SchedulingGenerationFacts,
)
from shared_kernel.money import MoneyNTD
from subsystems.orders.actual_start_workflow import (
    ActualStartApplyRequest,
    ActualStartWorkflow,
    ActualStartWorkflowContext,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.orders.terms_workflow import CommandClaimState
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionReceipt,
    HistoricalOrderAdoptionRequest,
    HistoricalOrderAdoptionWorkflow,
    HistoricalPairingResolution,
)
from subsystems.orders.terms_workflow import TermsWorkflowFacts
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.payroll.terms_impact import (
    CasePayrollPolicyTerms,
    PayrollTermsSourceFacts,
    SourceAssignmentPayrollTerms,
)


class _Repository:
    def load_order(self, case_no, client_name, *, for_update):
        del for_update
        assert (case_no, client_name) == ("CASE-1", "客戶甲")
        return HistoricalOrderCurrentFacts(
            "CASE-1",
            "客戶甲",
            OrderLifecycleStatus.DISCUSSION,
            3,
            date(2026, 8, 6),
            None,
            None,
        )

    def resolve_staff(self, name, *, for_update):
        del for_update
        return (11,) if name == "月嫂甲" else ()

    def active_assignments(self, case_no, *, for_update):
        del case_no, for_update
        return ()

    def find_receipt(self, key, source_identity):
        del key, source_identity
        return None


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _Writer:
    def append_completed_assignments(self, case_no, assignments):
        del case_no, assignments
        return ()


def _actual_start_facts(
    *,
    planned_start: date,
    current_actual_start: date,
    formal_start: date,
) -> ActualStartWorkflowContext:
    terms = OrderTerms(
        planned_start,
        1,
        8,
        MoneyNTD(0),
        ServiceTimeTerms(time(9), time(17), 0),
    )
    segment = EffectiveAssignmentSegment(
        assignment_id=51,
        staff_id=16,
        sequence=1,
        service_day_count=1,
        assigned_start_date=formal_start,
        assigned_end_date=formal_start,
        official_service_dates=(formal_start,),
    )
    shared = TermsWorkflowFacts(
        order=OrderAggregateFacts("CASE-1", 7, terms, False, "一般市民"),
        scheduling=SchedulingGenerationFacts(
            "CASE-1",
            3,
            3,
            (segment,),
            service_started=True,
        ),
        planned_service_dates=(formal_start,),
        planned_end_date=formal_start,
        client_finance=ClientFinanceTermsSourceFacts(
            "CASE-1",
            3,
            ClientPaymentTerms(
                0,
                MoneyNTD(300),
                date(2025, 9, 1),
                planned_start,
                None,
            ),
            (),
            (),
        ),
        payroll=PayrollTermsSourceFacts(
            "CASE-1",
            3,
            (
                SourceAssignmentPayrollTerms(
                    51,
                    16,
                    "policy-1",
                    PayrollPolicyKind.CITIZEN,
                ),
            ),
            (),
            None,
            CasePayrollPolicyTerms("policy-1", PayrollPolicyKind.CITIZEN),
        ),
        lifecycle=OrderLifecycleRootFacts(
            "CASE-1",
            OrderLifecycleStatus.ESTABLISHED,
            False,
            current_actual_start,
            False,
            False,
            False,
        ),
    )
    return ActualStartWorkflowContext(
        shared,
        ActualStartReconfirmationFacts(
            ActualStartReconfirmationState.NOT_REQUIRED,
            None,
            None,
            False,
        ),
    )


def test_deposit_paid_with_distinct_actual_start_builds_service_assignment_candidate():
    caregiver = SimpleNamespace(
        ordinal=1,
        name="月嫂甲",
        start_date=date(2026, 8, 7),
        end_date=date(2026, 9, 7),
        has_individual_interval=True,
        issue_codes=(),
    )
    row = SimpleNamespace(
        case_no="CASE-1",
        client_name="客戶甲",
        asserted_status=HistoricalOrderSourceStatus.DEPOSIT_PAID,
        actual_start_date=date(2026, 8, 7),
        actual_end_date=date(2026, 9, 7),
        issue_codes=(),
        caregivers=(caregiver,),
        source_identity="historical-orders:test:row:1",
        source_fingerprint="f" * 64,
    )

    preview = HistoricalOrderAdoptionWorkflow(
        _Repository(), _UnitOfWork, _Writer()
    ).preview(row)

    assert preview.after_status == OrderLifecycleStatus.ESTABLISHED.value
    assert preview.pairings[0].resolution is HistoricalPairingResolution.ASSIGNMENT_CANDIDATE
    assert preview.issue_codes == (
        "historical_accounting_service_calendar_unconfirmed",
    )


def test_matching_effective_assignment_is_reused_for_historical_actual_start():
    """Row 70 must not classify corroborating formal occupancy as a conflict."""
    asserted_start = date(2025, 10, 14)
    formal_end = date(2025, 11, 3)
    calls = []

    class Repository(_Repository):
        def __init__(self):
            self.current = HistoricalOrderCurrentFacts(
                "CASE-1", "客戶甲", OrderLifecycleStatus.DISCUSSION, 3,
                date(2025, 9, 10), date(2025, 9, 8), None,
            )

        def resolve_staff(self, name, *, for_update):
            del for_update
            return (16,) if name == "月嫂甲" else ()

        def active_assignments(self, case_no, *, for_update):
            del case_no, for_update
            return ({
                "id": 51,
                "staff_id": 16,
                "generation_id": 114,
                "assigned_start_date": asserted_start,
                "assigned_end_date": formal_end,
                "status": "completed",
            }, {
                "id": 40,
                "staff_id": 16,
                "generation_id": None,
                "assigned_start_date": date(2025, 9, 8),
                "assigned_end_date": date(2025, 10, 3),
                "status": "completed",
            })

        def load_order(self, case_no, client_name, *, for_update):
            del case_no, client_name, for_update
            return self.current

        def persist(self, request, preview, assignment_ids):
            del request
            calls.append(("persist", assignment_ids))
            assert assignment_ids == ()
            return HistoricalOrderAdoptionReceipt(
                preview.outcome, preview.case_no, preview.resulting_version,
                0, None, False, preview.fingerprint,
            )

    class Rebuilder:
        def preview(self, **values):
            calls.append(("preview", values))

        def apply_in_current_unit_of_work(self, **values):
            calls.append(("apply", values))

    row = SimpleNamespace(
        case_no="CASE-1", client_name="客戶甲",
        asserted_status=HistoricalOrderSourceStatus.DEPOSIT_PAID,
        actual_start_date=asserted_start, actual_end_date=date(2025, 10, 31),
        issue_codes=(),
        caregivers=(SimpleNamespace(
            ordinal=1, name="月嫂甲", start_date=asserted_start,
            end_date=date(2025, 10, 31), has_individual_interval=True,
            issue_codes=(),
        ),),
        source_identity="historical-orders:test:row:70",
        source_fingerprint="7" * 64,
    )
    repository = Repository()
    workflow = HistoricalOrderAdoptionWorkflow(
        repository, _UnitOfWork, _Writer(), Rebuilder()
    )

    preview = workflow.preview(row)
    assert preview.pairings[0].resolution is HistoricalPairingResolution.ASSIGNMENT_REUSED
    assert preview.issue_codes == (
        "historical_accounting_service_calendar_unconfirmed",
    )

    workflow.apply(HistoricalOrderAdoptionRequest(
        row, preview.fingerprint, "historical-order:row:70", "operator",
        "adopt row 70", "historical-order:row:70:correlation",
    ))
    assert calls == [("persist", ())]


def test_historical_actual_start_preview_projects_the_asserted_schedule_root():
    """A source assignment starts at the asserted, not HCM-planned, date."""
    asserted_start = date(2026, 8, 7)
    terms = OrderTerms(
        date(2026, 8, 6),
        1,
        8,
        MoneyNTD(0),
        ServiceTimeTerms(time(9), time(17), 0),
    )
    facts = TermsWorkflowFacts(
        order=OrderAggregateFacts("CASE-1", 3, terms, False, "一般市民"),
        scheduling=SchedulingGenerationFacts("CASE-1", 0, 0, ()),
        planned_service_dates=(),
        planned_end_date=date(2026, 8, 6),
        client_finance=ClientFinanceTermsSourceFacts(
            "CASE-1",
            0,
            ClientPaymentTerms(
                0,
                MoneyNTD(300),
                date(2026, 8, 1),
                date(2026, 8, 6),
                None,
            ),
            (),
            (),
        ),
        payroll=PayrollTermsSourceFacts(
            "CASE-1",
            0,
            (),
            (),
            None,
            CasePayrollPolicyTerms("policy-1", PayrollPolicyKind.CITIZEN),
        ),
        lifecycle=OrderLifecycleRootFacts(
            "CASE-1",
            OrderLifecycleStatus.DISCUSSION,
            False,
            None,
            False,
            False,
            False,
        ),
    )

    class Repository:
        def load_for_preview(self, case_no):
            assert case_no == "CASE-1"
            return ActualStartWorkflowContext(
                facts,
                ActualStartReconfirmationFacts(
                    ActualStartReconfirmationState.NOT_REQUIRED,
                    None,
                    None,
                    False,
                ),
            )

    class Clock:
        def now(self):
            return datetime(2026, 8, 1, tzinfo=timezone.utc)

    preview = ActualStartWorkflow(Repository(), object, Clock()).preview_historical_source(
        "CASE-1",
        asserted_start,
        recalculated_service_dates=(asserted_start,),
        source_staff_ids=(11,),
    )

    assert preview.actual_start.new_actual_start_date == asserted_start
    assert preview.scheduling.assignments[0].assigned_start_date == asserted_start


def test_historical_preview_corrects_a_stale_order_root_against_formal_schedule():
    asserted_start = date(2025, 10, 14)
    facts = _actual_start_facts(
        planned_start=date(2025, 9, 10),
        current_actual_start=date(2025, 9, 8),
        formal_start=asserted_start,
    )

    class Repository:
        def load_for_preview(self, _case_no):
            return facts

    class Clock:
        def now(self):
            return datetime(2025, 9, 1, tzinfo=timezone.utc)

    preview = ActualStartWorkflow(Repository(), object, Clock()).preview_historical_source(
        "CASE-1",
        asserted_start,
        recalculated_service_dates=(asserted_start,),
        source_staff_ids=(),
    )

    assert preview.before_actual_start_date == asserted_start
    assert preview.actual_start.original_scheduling_root_date == asserted_start
    assert preview.actual_start.new_actual_start_date == asserted_start


def test_legacy_actual_start_apply_rejects_stale_root_even_with_historical_dates():
    """Negative control: the generic Apply path cannot consume this source context."""
    asserted_start = date(2025, 10, 14)
    facts = _actual_start_facts(
        planned_start=date(2025, 9, 10),
        current_actual_start=date(2025, 9, 8),
        formal_start=asserted_start,
    )

    class Repository:
        def preflight_impacted_staff_ids(self, _case_no):
            return (16,)

        def claim_actual_start_command(self, _request, _fingerprint):
            return CommandClaimState.CREATED

        def find_actual_start_receipt(self, _key, *, for_update):
            assert for_update is True
            return None

        def load_for_apply(self, _case_no, _staff_ids):
            return facts

    request = ActualStartApplyRequest(
        "CASE-1",
        asserted_start,
        ExpectedVersion(7),
        ExpectedVersion(3),
        ExpectedVersion(3),
        ExpectedVersion(3),
        fingerprint_payload({"preview": "historical"}),
        IdempotencyKey("historical-negative-control"),
        ActorContext("operator"),
        "historical actual start",
        CorrelationId("historical-negative-control"),
    )

    with pytest.raises(ActualStartCandidateError) as caught:
        ActualStartWorkflow(Repository(), object, object()).apply_in_current_unit_of_work(
            request,
            recalculated_service_dates=(asserted_start,),
        )

    assert caught.value.blocker.value == "scheduling_root_mismatch"


def test_historical_apply_rebuilds_fresh_candidate_from_formal_schedule_context():
    asserted_start = date(2025, 10, 14)
    facts = _actual_start_facts(
        planned_start=date(2025, 9, 10),
        current_actual_start=date(2025, 9, 8),
        formal_start=asserted_start,
    )

    class Repository:
        def load_for_preview(self, _case_no):
            return facts

        def preflight_impacted_staff_ids(self, _case_no):
            return (16,)

        def claim_actual_start_command(self, _request, _fingerprint):
            return CommandClaimState.CREATED

        def find_actual_start_receipt(self, _key, *, for_update):
            assert for_update is True
            return None

        def load_for_apply(self, _case_no, staff_ids):
            assert staff_ids == (16,)
            return facts

    class Clock:
        def now(self):
            return datetime(2025, 9, 1, tzinfo=timezone.utc)

    workflow = ActualStartWorkflow(Repository(), object, Clock())
    historical_preview = workflow.preview_historical_source(
        "CASE-1",
        asserted_start,
        recalculated_service_dates=(asserted_start,),
        source_staff_ids=(),
    )
    request = ActualStartApplyRequest(
        "CASE-1",
        asserted_start,
        ExpectedVersion(historical_preview.order_version),
        ExpectedVersion(historical_preview.scheduling_version),
        ExpectedVersion(historical_preview.client_finance_version),
        ExpectedVersion(historical_preview.payroll_version),
        historical_preview.fingerprint,
        IdempotencyKey("historical-source-context-apply"),
        ActorContext("operator"),
        "historical actual start",
        CorrelationId("historical-source-context-apply"),
    )
    persisted = {}
    workflow._persist = lambda _request, preview, *_args: persisted.setdefault(
        "preview", preview
    )

    workflow.apply_historical_source_in_current_unit_of_work(
        request,
        recalculated_service_dates=(asserted_start,),
        source_staff_ids=(),
    )

    assert persisted["preview"].actual_start.original_scheduling_root_date == asserted_start
    assert persisted["preview"].actual_start.new_actual_start_date == asserted_start


def test_historical_source_context_reuses_bridged_formal_assignment_identity():
    asserted_start = date(2025, 10, 14)
    facts = _actual_start_facts(
        planned_start=date(2025, 9, 10),
        current_actual_start=date(2025, 9, 8),
        formal_start=asserted_start,
    )

    class Repository:
        def load_for_preview(self, _case_no):
            return facts

    class Clock:
        def now(self):
            return datetime(2025, 9, 1, tzinfo=timezone.utc)

    preview = ActualStartWorkflow(Repository(), object, Clock()).preview_historical_source(
        "CASE-1",
        asserted_start,
        recalculated_service_dates=(asserted_start,),
        source_staff_ids=(16,),
    )

    assert preview.actual_start.assignments[0].source_assignment_id == 51


def test_deposit_paid_without_service_evidence_adopts_status_but_defers_actual_start():
    row = SimpleNamespace(
        case_no="CASE-1",
        client_name="客戶甲",
        asserted_status=HistoricalOrderSourceStatus.DEPOSIT_PAID,
        actual_start_date=date(2026, 8, 7),
        actual_end_date=date(2026, 9, 7),
        issue_codes=(),
        caregivers=(),
        source_identity="historical-orders:test:missing-service-evidence",
        source_fingerprint="e" * 64,
    )

    preview = HistoricalOrderAdoptionWorkflow(
        _Repository(), _UnitOfWork, _Writer()
    ).preview(row)

    assert preview.after_status == OrderLifecycleStatus.ESTABLISHED.value
    assert preview.date_patch == ()
    assert preview.issue_codes == ("historical_actual_start_evidence_insufficient",)


def test_deposit_paid_historical_period_skips_precision_and_requires_accounting_review():
    """Historical roots advance without inventing a daily calendar or accounting."""
    actual_start_date = date(2026, 8, 7)
    timeline: list[tuple[str, object]] = []

    class Repository(_Repository):
        def __init__(self):
            self.current = HistoricalOrderCurrentFacts(
                "CASE-1",
                "客戶甲",
                OrderLifecycleStatus.DISCUSSION,
                3,
                date(2026, 8, 6),
                None,
                None,
            )
            self.lifecycle_events: list[tuple[str, str, int]] = []

        def load_order(self, case_no, client_name, *, for_update):
            del for_update
            assert (case_no, client_name) == ("CASE-1", "客戶甲")
            return self.current

        def persist(self, request, preview, assignment_ids):
            del request
            assert assignment_ids == ()
            timeline.append(("status-transition", preview.after_status))
            self.lifecycle_events.append(
                (preview.before_status, preview.after_status, preview.resulting_version)
            )
            self.current = HistoricalOrderCurrentFacts(
                "CASE-1",
                "客戶甲",
                OrderLifecycleStatus(preview.after_status),
                preview.resulting_version,
                date(2026, 8, 6),
                actual_start_date,
                row.actual_end_date,
            )
            return HistoricalOrderAdoptionReceipt(
                preview.outcome,
                preview.case_no,
                preview.resulting_version,
                0,
                None,
                False,
                preview.fingerprint,
            )

    class ForbiddenPrecision:
        def preview(self, **_values):
            raise AssertionError("historical import must not calculate service days")

        def apply_in_current_unit_of_work(self, **_values):
            raise AssertionError("historical import must not project accounting")

    row = SimpleNamespace(
        case_no="CASE-1",
        client_name="客戶甲",
        asserted_status=HistoricalOrderSourceStatus.DEPOSIT_PAID,
        actual_start_date=actual_start_date,
        actual_end_date=date(2026, 9, 7),
        issue_codes=(),
        caregivers=(
            SimpleNamespace(
                ordinal=1,
                name="月嫂甲",
                start_date=actual_start_date,
                end_date=date(2026, 9, 7),
                has_individual_interval=True,
                issue_codes=(),
            ),
        ),
        source_identity="historical-orders:test:actual-service-dates",
        source_fingerprint="f" * 64,
    )
    repository = Repository()
    workflow = HistoricalOrderAdoptionWorkflow(
        repository,
        _UnitOfWork,
        _Writer(),
        ForbiddenPrecision(),
    )

    preview = workflow.preview(row)

    assert preview.after_status == OrderLifecycleStatus.ESTABLISHED.value
    assert preview.pairings[0].resolution is HistoricalPairingResolution.ASSIGNMENT_CANDIDATE
    assert preview.date_patch == (
        ("actual_start_date", actual_start_date),
        ("actual_end_date", row.actual_end_date),
    )
    assert preview.issue_codes == (
        "historical_accounting_service_calendar_unconfirmed",
    )
    assert timeline == []

    receipt = workflow.apply(
        HistoricalOrderAdoptionRequest(
            row,
            preview.fingerprint,
            "historical-order:actual-service-dates",
            "test-operator",
            "adopt historical roots without precision",
            "historical-order:actual-service-dates:correlation",
        )
    )

    assert receipt.resulting_version == 4
    assert repository.lifecycle_events == [
        (OrderLifecycleStatus.DISCUSSION.value, OrderLifecycleStatus.ESTABLISHED.value, 4)
    ]
    assert timeline == [("status-transition", OrderLifecycleStatus.ESTABLISHED.value)]
