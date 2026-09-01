from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import SimpleNamespace

from domains.client_finance.obligation_planning import (
    ClientFinanceTermsSourceFacts,
    ClientPaymentTerms,
)
from domains.orders.actual_start import (
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
from domains.scheduling.generation import SchedulingGenerationFacts
from shared_kernel.money import MoneyNTD
from subsystems.orders.actual_start_workflow import (
    ActualStartWorkflow,
    ActualStartWorkflowContext,
)
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionReceipt,
    HistoricalOrderAdoptionRequest,
    HistoricalOrderAdoptionWorkflow,
    HistoricalPairingResolution,
)
from subsystems.orders.historical_actual_start_rebuild import (
    HistoricalActualStartRebuilder,
)
from subsystems.orders.terms_workflow import TermsWorkflowFacts
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.payroll.terms_impact import (
    CasePayrollPolicyTerms,
    PayrollTermsSourceFacts,
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
    assert preview.issue_codes == ()


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


def test_deposit_paid_actual_service_dates_rebuild_after_status_adoption():
    """A status-1 row uses its own verified caregiver evidence during Apply."""
    actual_start_date = date(2026, 8, 7)
    official_service_dates = (date(2026, 8, 7), date(2026, 8, 10))
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
                None,
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

    class Planner:
        def calculate(self, case_no, candidate_start, *, for_update):
            assert (case_no, candidate_start) == ("CASE-1", actual_start_date)
            timeline.append(("service-date-calculate", for_update))
            return official_service_dates

        def preview_source_generation(
            self, case_no, service_dates, *, source_staff_ids=()
        ):
            assert (case_no, service_dates) == ("CASE-1", official_service_dates)
            assert source_staff_ids == (11,)
            timeline.append(("service-date-source-validated", service_dates))

        def prepare_source_generation(
            self,
            case_no,
            service_dates,
            *,
            source_identity,
            actor,
            correlation_id,
        ):
            assert (case_no, service_dates) == ("CASE-1", official_service_dates)
            assert source_identity == row.source_identity
            assert actor == "test-operator"
            assert correlation_id == "historical-order:actual-service-dates:correlation"
            timeline.append(("service-date-source-prepared", service_dates))

    class CanonicalActualStart:
        def replay_from_immutable_source(self, _idempotency_key):
            return None

        def preview(self, case_no, candidate_start, *, recalculated_service_dates):
            assert (case_no, candidate_start, recalculated_service_dates) == (
                "CASE-1",
                actual_start_date,
                official_service_dates,
            )
            timeline.append(("actual-service-dates-previewed", recalculated_service_dates))
            return SimpleNamespace(
                order_version=4,
                scheduling_version=5,
                client_finance_version=6,
                payroll_version=7,
                fingerprint=fingerprint_payload({"actual-start": "preview"}),
            )

        def preview_historical_source(
            self,
            case_no,
            candidate_start,
            *,
            recalculated_service_dates,
            source_staff_ids,
        ):
            assert (case_no, candidate_start, recalculated_service_dates) == (
                "CASE-1",
                actual_start_date,
                official_service_dates,
            )
            assert source_staff_ids == (11,)
            timeline.append(("actual-service-dates-previewed", recalculated_service_dates))

        def apply_in_current_unit_of_work(self, request, *, recalculated_service_dates):
            assert request.new_actual_start_date == actual_start_date
            assert recalculated_service_dates == official_service_dates
            timeline.append(("actual-service-dates-applied", recalculated_service_dates))

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
        HistoricalActualStartRebuilder(CanonicalActualStart(), Planner()),
    )

    preview = workflow.preview(row)

    assert preview.after_status == OrderLifecycleStatus.ESTABLISHED.value
    assert preview.pairings[0].resolution is HistoricalPairingResolution.ASSIGNMENT_CANDIDATE
    assert timeline == [
        ("service-date-calculate", False),
        ("service-date-source-validated", official_service_dates),
        ("actual-service-dates-previewed", official_service_dates),
    ]

    receipt = workflow.apply(
        HistoricalOrderAdoptionRequest(
            row,
            preview.fingerprint,
            "historical-order:actual-service-dates",
            "test-operator",
            "validate service dates before lifecycle transition",
            "historical-order:actual-service-dates:correlation",
        )
    )

    assert receipt.resulting_version == 4
    assert repository.lifecycle_events == [
        (OrderLifecycleStatus.DISCUSSION.value, OrderLifecycleStatus.ESTABLISHED.value, 4)
    ]
    assert timeline == [
        ("service-date-calculate", False),
        ("service-date-source-validated", official_service_dates),
        ("actual-service-dates-previewed", official_service_dates),
        ("service-date-calculate", False),
        ("service-date-source-validated", official_service_dates),
        ("actual-service-dates-previewed", official_service_dates),
        ("status-transition", OrderLifecycleStatus.ESTABLISHED.value),
        ("service-date-calculate", True),
        ("service-date-source-prepared", official_service_dates),
        ("actual-service-dates-previewed", official_service_dates),
        ("actual-service-dates-applied", official_service_dates),
    ]
