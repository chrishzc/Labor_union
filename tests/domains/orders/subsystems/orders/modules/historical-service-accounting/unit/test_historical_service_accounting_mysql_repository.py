"""Read and snapshot persistence for historical service-day comparisons."""

from datetime import date, time
from dataclasses import replace
from decimal import Decimal
from contextlib import contextmanager
import json
import pytest

from domains.orders.historical_service_accounting import HistoricalActualServiceDaysInput
from domains.orders.historical_service_accounting import HistoricalAssignmentServiceFact
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import PayrollPolicyKind, rate_snapshot
from infrastructure.mysql.historical_service_accounting_repository import MySqlHistoricalServiceAccountingRepository
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.orders.historical_service_accounting_workflow import (
    ApplyHistoricalServiceAccounting,
    ConfirmHistoricalServiceDaysIntent,
    HistoricalServiceAccountingAssignmentFacts,
    HistoricalServiceAccountingFacts,
    HistoricalServiceAccountingBaseline,
    HistoricalServiceFactsCorrectionCandidate,
    _candidate,
    HistoricalAttributionIntent, HistoricalServiceAccountingWorkflow,
)
from subsystems.client_finance.pricing_configuration import HistoricalRepricingPlan
from subsystems.client_finance.pricing_configuration import HistoricalPersonPricing


class _LoadCursor:
    def __init__(self):
        self.statements = []
        self._one = None
        self._all = ()

    def execute(self, statement, parameters):
        normalized = " ".join(statement.split())
        self.statements.append((normalized, parameters))
        if "FROM orders o JOIN clients c" in statement:
            self._one = {
                "case_no": "CASE-19",
                "status": OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value,
                "lifecycle_version": 3,
                "service_days": 40,
                "service_hours_per_day": 9,
                "floor_fee": 4_000,
                "identity_status": "一般市民",
                "client_finance_version": 2,
                "payroll_version": 4,
                "adoption_receipt_id": 19,
                "source_event_identity": "historical-source:19",
                "historical_day_revision": 1,
                "client_policy_version": "client-policy:case-19",
                "client_hourly_rate_ntd": 275,
                "completed_on": date(2026, 4, 20),
                "staff_payment_due_date": None,
            }
        elif "FROM historical_order_pairing_evidence evidence" in statement:
            self._all = ({
                "assignment_id": 19,
                "staff_id": 3,
                "staff_name": "月嫂甲",
                "payroll_policy_version": "policy:1",
                "payroll_policy_kind": PayrollPolicyKind.CITIZEN.value,
                "payroll_hourly_rate_ntd": 300,
            },)
        elif "FROM payroll_adjustment_allocations" in statement:
            self._all = ({"assignment_id": 19, "amount_ntd": 150},)

    def fetchone(self):
        value, self._one = self._one, None
        return value

    def fetchall(self):
        value, self._all = self._all, ()
        return value

    def close(self):
        return None


class _LoadConnection:
    def __init__(self):
        self.cursor_instance = _LoadCursor()

    def cursor(self):
        return self.cursor_instance


def _candidate_and_request():
    facts = HistoricalServiceAccountingFacts(
        case_no="CASE-19",
        lifecycle_status=OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        lifecycle_version=3,
        adoption_receipt_id=19,
        adoption_source_identity="historical-source:19",
        historical_day_revision=0,
        client_finance_version=2,
        payroll_version=4,
        contracted_service_days=40,
        service_hours_per_day=9,
        contractual_floor_fee=MoneyNTD(4_000),
        client_identity_status="一般市民",
        assignments=(
            HistoricalServiceAccountingAssignmentFacts(
                "assignment:19",
                3,
                "月嫂甲",
                rate_snapshot(
                    "assignment:19", "policy:1", PayrollPolicyKind.CITIZEN
                ),
                MoneyNTD(0),
            ),
        ),
        client_policy_version="client-policy:case-19",
        client_hourly_rate=MoneyNTD(300),
        completed_on=date(2026, 4, 20),
        staff_payment_due_date=None,
    )
    intent = ConfirmHistoricalServiceDaysIntent(
        "CASE-19",
        (HistoricalActualServiceDaysInput("assignment:19", 3, 3),),
    )
    candidate = _candidate(facts, intent)
    request = ApplyHistoricalServiceAccounting(
        intent,
        3,
        0,
        2,
        4,
        candidate.fingerprint,
        IdempotencyKey("historical-days:19:revision:1"),
        ActorContext("operator"),
        "確認舊系統實際服務天數",
        CorrelationId("historical-days:19:revision:1"),
    )
    return candidate, request


def test_load_uses_case_client_terms_and_assignment_owned_payroll_facts():
    connection = _LoadConnection()

    facts = MySqlHistoricalServiceAccountingRepository(connection).load(
        "CASE-19", for_update=True
    )

    assert facts.client_policy_version == "client-policy:case-19"
    assert facts.client_hourly_rate == MoneyNTD(275)
    assert facts.assignments[0].rate_snapshot.hourly_rate == MoneyNTD(300)
    assert facts.assignments[0].effective_adjustment == MoneyNTD(150)
    statements = tuple(statement for statement, _ in connection.cursor_instance.statements)
    assert any("JOIN client_payment_terms client_terms" in statement for statement in statements)
    assert any("LEFT JOIN assignment_payroll_rate_snapshots rate" in statement for statement in statements)
    assert any("JOIN case_payroll_rate_policy_snapshots case_rate" in statement for statement in statements)
    assert any("FROM payroll_adjustment_allocations" in statement for statement in statements)
    assert all(statement.endswith("FOR UPDATE") for statement in statements)


def test_persist_writes_only_service_day_revision_and_comparison_snapshot():
    class RecordingCursor:
        lastrowid = 41

        def __init__(self):
            self.writes = []

        def execute(self, statement, parameters):
            self.writes.append((statement, parameters))

        executemany = execute

        def close(self):
            pass

    connection = _LoadConnection()
    connection.cursor_instance = RecordingCursor()
    candidate, request = _candidate_and_request()

    receipt = MySqlHistoricalServiceAccountingRepository(connection).persist(request, candidate)

    assert receipt.resulting_historical_day_revision == 1
    assert receipt.resulting_client_finance_version == 2
    assert receipt.resulting_payroll_version == 4
    assert receipt.client_obligation_amount_ntd == 8400
    assert receipt.staff_obligation_amount_ntd == 8400
    assert [statement.split()[2] for statement, _ in connection.cursor_instance.writes] == [
        "historical_service_day_events",
        "historical_service_day_items",
        "historical_service_day_projections",
        "historical_service_accounting_outbox",
    ]


def _completed_period():
    return HistoricalAssignmentServiceFact(
        "assignment:19", 3, date(2026, 3, 1), date(2026, 4, 20), time(8), time(16), Decimal("8"),
    )


def test_completed_fact_uses_confirmed_hours_without_deriving_days_from_dates():
    candidate, _ = _candidate_and_request()
    second = replace(candidate.facts.assignments[0], assignment_identity="assignment:20", staff_id=4,
                     rate_snapshot=replace(candidate.facts.assignments[0].rate_snapshot, assignment_identity="assignment:20"),
                     actual_service_days=2, actual_service_hours=Decimal("15"),
                     service_fact=replace(_completed_period(), assignment_identity="assignment:20",
                                          staff_id=4, service_hours_per_day=Decimal("7.5")))
    facts = replace(candidate.facts, assignments=(candidate.facts.assignments[0], second))
    intent = ConfirmHistoricalServiceDaysIntent(facts.case_no, (
        HistoricalActualServiceDaysInput("assignment:19", 3, 3),
        HistoricalActualServiceDaysInput("assignment:20", 4, 2),
    ), (_completed_period(),))
    revised = _candidate(facts, intent, attribution=True)
    assert revised.service_days.total_actual_service_days == 5
    assert revised.service_days.total_actual_service_hours == Decimal("39")
    assert [item.actual_service_hours for item in revised.service_days.allocations] == [Decimal("24"), Decimal("15")]
    assert [item.actual_hours for item in revised.payroll.assignments] == [24, 15]
    assert revised.service_days.allocations[1].service_fact == second.service_fact
    assert revised.facts.assignments[1] == second
    assert revised.client_finance.actual_service_hours == 39
    assert revised.facts.completed_on == candidate.facts.completed_on
    assert revised.facts.assignments[0].rate_snapshot == candidate.facts.assignments[0].rate_snapshot


@pytest.mark.parametrize("changes", [
    {"service_hours_per_day": Decimal("NaN")}, {"service_hours_per_day": Decimal("0")},
    {"service_hours_per_day": Decimal("8.25")}, {"actual_end_date": date(2026, 2, 1)},
    {"service_end_time": time(7)},
])
def test_completed_fact_rejects_invalid_dates_hours_or_same_day_shift(changes):
    with pytest.raises(ValueError):
        replace(_completed_period(), **changes)


def test_completed_fact_preview_has_no_writes_and_stale_apply_has_no_partial_writes():
    candidate, request = _candidate_and_request()
    facts = replace(candidate.facts, assignments=(replace(candidate.facts.assignments[0],
                    actual_service_days=3, actual_service_hours=Decimal("27")),))

    class Repository:
        writes = 0

        def load(self, case_no, *, for_update):
            return self.facts

        def preview_service_volume(self, case_no, before, after, *, for_update):
            assert before == {"assignment:19": Decimal("27")}
            assert after == {"assignment:19": Decimal("24")}
            return HistoricalRepricingPlan(case_no, 2, None, (), (), pending=("original_payout_missing",))

        def lock_attribution_order(self, case_no):
            pass

        def find_receipt(self, key):
            return None

        def persist_attribution(self, *args, **kwargs):
            self.writes += 1

    repository = Repository()
    repository.facts = facts

    @contextmanager
    def unit():
        yield object()

    workflow = HistoricalServiceAccountingWorkflow(repository, unit)
    intent = HistoricalAttributionIntent(facts.case_no, ((3, 3),), "逐人服務證據", (_completed_period(),))
    preview = workflow.preview_attribution(intent)
    assert preview.accounting_pending == ("original_payout_missing",)
    assert repository.writes == 0
    repository.facts = replace(facts, lifecycle_version=facts.lifecycle_version + 1)
    with pytest.raises(ValueError, match="historical_attribution_preview_stale"):
        workflow.apply_attribution(intent, preview.fingerprint, actor=request.actor, reason=request.reason,
                                   key=request.idempotency_key, correlation=request.correlation_id)
    assert repository.writes == 0


@pytest.mark.parametrize("status", [
    OrderLifecycleStatus.HISTORICAL_IN_SERVICE, OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    OrderLifecycleStatus.CANCELLED,
])
def test_completed_fact_does_not_expand_other_lifecycle_states(status):
    candidate, _ = _candidate_and_request()
    facts = replace(candidate.facts, lifecycle_status=status)

    class Repository:
        def load(self, *args, **kwargs):
            return facts

    workflow = HistoricalServiceAccountingWorkflow(Repository(), lambda: None)
    intent = HistoricalAttributionIntent(facts.case_no, ((3, 3),), "逐人服務證據", (_completed_period(),))
    with pytest.raises(ValueError, match="historical_completed_service_correction_status_invalid"):
        workflow.preview_attribution(intent)


def test_completed_fact_preserves_every_adopted_day_and_assignment_identity():
    candidate, _ = _candidate_and_request()
    facts = replace(candidate.facts, assignments=(replace(candidate.facts.assignments[0],
                    actual_service_days=3, actual_service_hours=Decimal("27")),))

    class Repository:
        def load(self, case_no, *, for_update):
            return facts

    workflow = HistoricalServiceAccountingWorkflow(Repository(), lambda: None)
    with pytest.raises(ValueError, match="historical_completed_service_days_must_be_preserved"):
        workflow.preview_attribution(HistoricalAttributionIntent(
            facts.case_no, ((3, 4),), "逐人服務證據", (_completed_period(),)))
    with pytest.raises(ValueError, match="historical_completed_service_assignment_mismatch"):
        workflow.preview_attribution(HistoricalAttributionIntent(
            facts.case_no, ((3, 3),), "逐人服務證據",
            (replace(_completed_period(), staff_id=4),)))


def test_completed_fact_apply_saves_financial_plan_once_and_replay_is_original_receipt():
    candidate, request = _candidate_and_request()
    facts = replace(candidate.facts, assignments=(replace(candidate.facts.assignments[0],
                    actual_service_days=3, actual_service_hours=Decimal("27")),))
    calls = []

    class Repository:
        stored = None

        def load(self, case_no, *, for_update):
            calls.append(("load", for_update))
            return facts

        def preview_service_volume(self, case_no, before, after, *, for_update):
            calls.append(("financial_preview", for_update))
            return HistoricalRepricingPlan(case_no, 2, 4, (), (), pending=("missing_client_source",))

        def lock_attribution_order(self, case_no):
            calls.append(("lock", case_no))

        def find_receipt(self, key):
            return self.stored

        def persist_attribution(self, intent, preview, command, **kwargs):
            from subsystems.orders.historical_service_accounting_workflow import (
                HistoricalServiceAccountingReceipt, StoredHistoricalServiceAccountingReceipt,
            )
            assert preview.payroll is None
            assert preview.volume_repricing is not None
            assert preview.accounting_pending == ("missing_client_source",)
            receipt = HistoricalServiceAccountingReceipt(
                facts.case_no, 1, 2, 4, 3, 8400, 8400, preview.fingerprint,
                accounting_pending=preview.accounting_pending,
            )
            self.stored = StoredHistoricalServiceAccountingReceipt(command, receipt)
            calls.append(("persist", intent.service_facts))
            return receipt

    class Unit:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def commit(self):
            calls.append(("commit",))

    repository = Repository()
    workflow = HistoricalServiceAccountingWorkflow(repository, Unit)
    intent = HistoricalAttributionIntent(facts.case_no, ((3, 3),), "逐人服務證據", (_completed_period(),))
    preview = workflow.preview_attribution(intent)
    assert not any(item[0] in {"persist", "commit"} for item in calls)
    receipt = workflow.apply_attribution(intent, preview.fingerprint, actor=request.actor, reason=request.reason,
                                         key=request.idempotency_key, correlation=request.correlation_id)
    replay = workflow.apply_attribution(intent, preview.fingerprint, actor=request.actor, reason=request.reason,
                                        key=request.idempotency_key, correlation=request.correlation_id)
    assert receipt.accounting_pending == replay.accounting_pending == ("missing_client_source",)
    assert replay.replayed is True
    assert sum(item[0] == "persist" for item in calls) == 1
    assert sum(item[0] == "commit" for item in calls) == 1
    assert ("load", True) in calls and ("financial_preview", True) in calls


def _partial_completed_facts():
    candidate, request = _candidate_and_request()
    known = replace(candidate.facts.assignments[0], actual_service_days=3, actual_service_hours=Decimal("27"))
    unknown = replace(known, assignment_identity="assignment:20", staff_id=4, staff_name="月嫂乙",
                      rate_snapshot=replace(known.rate_snapshot, assignment_identity="assignment:20"),
                      actual_service_days=None, actual_service_hours=None)
    return replace(candidate.facts, historical_day_revision=1, assignments=(known, unknown),
                   service_baseline=HistoricalServiceAccountingBaseline(41, 40, Decimal("360"), 4000, 99000, 108000)), request


@pytest.mark.parametrize("selected_staff", [3, 4])
def test_partial_completed_facts_preview_keeps_unknown_sibling_and_dates_separate_from_days(selected_staff):
    facts, _ = _partial_completed_facts()
    selected = replace(_completed_period(), assignment_identity=f"assignment:{19 if selected_staff == 3 else 20}",
                       staff_id=selected_staff)

    class Repository:
        def load(self, case_no, *, for_update):
            return facts

        def preview_service_volume(self, case_no, before, after, *, for_update):
            assert not for_update
            assert before == {"assignment:19": Decimal("27")}
            assert after == {"assignment:19": Decimal("24" if selected_staff == 3 else "27")}
            return HistoricalRepricingPlan(case_no, 2, 4, (), (), persons=(
                HistoricalPersonPricing("assignment:19", 3, "月嫂甲", after["assignment:19"], 8100,
                                        7200 if selected_staff == 3 else 8100, -900 if selected_staff == 3 else 0),
                HistoricalPersonPricing("assignment:20", 4, "月嫂乙", None, None, None, None),
            ), pending=("historical_pricing_total_service_hours_required",))

    intent = HistoricalAttributionIntent(facts.case_no, ((3, 3),) if selected_staff == 3 else (), "逐人服務證據", (selected,))
    result = HistoricalServiceAccountingWorkflow(Repository(), lambda: None).preview_attribution(intent)
    assert isinstance(result.comparison, HistoricalServiceFactsCorrectionCandidate)
    assert result.comparison.service_facts == (selected,)
    assert result.comparison.facts.assignments == facts.assignments
    assert result.comparison.facts.assignments[1].actual_service_days is None
    assert result.comparison.facts.assignments[1].actual_service_hours is None
    assert result.volume_repricing.persons[1].after_amount is None
    assert "historical_completed_service_volume_unresolved:assignment:20" in result.accounting_pending
    assert result.comparison.facts.service_baseline.total_actual_service_hours == Decimal("360")


def test_partial_completed_facts_without_previous_event_returns_specific_storage_gap():
    facts, _ = _partial_completed_facts()

    class Repository:
        def load(self, case_no, *, for_update):
            return replace(facts, service_baseline=None, historical_day_revision=0)

    workflow = HistoricalServiceAccountingWorkflow(Repository(), lambda: None)
    with pytest.raises(ValueError, match="historical_completed_service_partial_baseline_required"):
        workflow.preview_attribution(HistoricalAttributionIntent(
            facts.case_no, ((3, 3),), "逐人服務證據", (_completed_period(),)))


def test_query_canonicalizes_assignment_identities_without_swapping_service_or_payroll_facts():
    first_period = replace(_completed_period(), assignment_identity="assignment:9")
    second_period = replace(
        _completed_period(), assignment_identity="assignment:10", staff_id=4,
        actual_start_date=date(2026, 4, 1),
    )

    class Cursor(_LoadCursor):
        def execute(self, statement, parameters):
            super().execute(statement, parameters)
            if "FROM orders o JOIN clients c" in statement:
                self._one["day_result_snapshot"] = {
                    "service_facts": [first_period.canonical_payload(), second_period.canonical_payload()],
                }
            elif "FROM historical_order_pairing_evidence evidence" in statement:
                initial = self._all[0]
                self._all = (
                    {**initial, "assignment_id": 9, "actual_service_days": 3, "actual_service_hours": Decimal("24")},
                    {**initial, "assignment_id": 10, "staff_id": 4, "staff_name": "月嫂乙",
                     "payroll_policy_version": "policy:2",
                     "payroll_policy_kind": PayrollPolicyKind.SUBSIDIZED_CITIZEN.value,
                     "payroll_hourly_rate_ntd": 350,
                     "actual_service_days": 2, "actual_service_hours": Decimal("16")},
                )
            elif "FROM payroll_adjustment_allocations" in statement:
                self._all = ({"assignment_id": 9, "amount_ntd": 150}, {"assignment_id": 10, "amount_ntd": 200})

    connection = _LoadConnection()
    connection.cursor_instance = Cursor()
    workflow = HistoricalServiceAccountingWorkflow(
        MySqlHistoricalServiceAccountingRepository(connection), lambda: None,
    )

    facts = workflow.query("CASE-19")

    assert tuple(item.assignment_identity for item in facts.assignments) == ("assignment:10", "assignment:9")
    assignment_ten, assignment_nine = facts.assignments
    assert (assignment_ten.staff_id, assignment_ten.staff_name) == (4, "月嫂乙")
    assert assignment_ten.rate_snapshot == rate_snapshot(
        "assignment:10", "policy:2", PayrollPolicyKind.SUBSIDIZED_CITIZEN,
    )
    assert assignment_ten.rate_snapshot.hourly_rate == MoneyNTD(350)
    assert assignment_ten.effective_adjustment == MoneyNTD(200)
    assert (assignment_ten.actual_service_days, assignment_ten.actual_service_hours) == (2, Decimal("16"))
    assert assignment_ten.service_fact == second_period
    assert (assignment_nine.staff_id, assignment_nine.staff_name) == (3, "月嫂甲")
    assert assignment_nine.rate_snapshot == rate_snapshot(
        "assignment:9", "policy:1", PayrollPolicyKind.CITIZEN,
    )
    assert assignment_nine.rate_snapshot.hourly_rate == MoneyNTD(300)
    assert assignment_nine.effective_adjustment == MoneyNTD(150)
    assert (assignment_nine.actual_service_days, assignment_nine.actual_service_hours) == (3, Decimal("24"))
    assert assignment_nine.service_fact == first_period


def test_partial_completed_query_reads_confirmed_dates_without_inventing_sibling_volume():
    period = replace(_completed_period(), assignment_identity="assignment:20", staff_id=4)

    class Cursor(_LoadCursor):
        def execute(self, statement, parameters):
            super().execute(statement, parameters)
            if "FROM orders o JOIN clients c" in statement:
                self._one = {**self._one, "day_event_id": 41, "day_total_actual_service_days": 40,
                    "day_total_actual_service_hours": Decimal("360"), "day_historical_floor_fee_ntd": 4000,
                    "day_client_obligation_amount_ntd": 99000, "day_staff_obligation_amount_ntd": 108000,
                    "day_result_snapshot": {"service_facts": [period.canonical_payload()],
                        "accounting_pending": ["historical_completed_service_volume_unresolved:assignment:20"]}}
            elif "FROM historical_order_pairing_evidence evidence" in statement:
                first = {**self._all[0], "actual_service_days": 3, "actual_service_hours": Decimal("27")}
                self._all = (first, {**first, "assignment_id": 20, "staff_id": 4, "staff_name": "月嫂乙",
                                    "actual_service_days": None, "actual_service_hours": None})

    connection = _LoadConnection()
    connection.cursor_instance = Cursor()
    facts = MySqlHistoricalServiceAccountingRepository(connection).load("CASE-19", for_update=False)
    assert facts.assignments[0].actual_service_days == 3
    assert facts.assignments[0].actual_service_hours == Decimal("27")
    assert facts.assignments[1].service_fact == period
    assert facts.assignments[1].actual_service_days is None
    assert facts.assignments[1].actual_service_hours is None
    assert facts.service_baseline.event_id == 41
    assert facts.accounting_pending == ("historical_completed_service_volume_unresolved:assignment:20",)


def test_partial_completed_persistence_copies_existing_items_without_materializing_unknown_person(monkeypatch):
    facts, request = _partial_completed_facts()
    plan = HistoricalRepricingPlan(facts.case_no, 2, 4, (), (), persons=(
        HistoricalPersonPricing("assignment:19", 3, "月嫂甲", Decimal("24"), 8100, 7200, -900),
    ), pending=(
        "historical_completed_service_volume_unresolved:assignment:20",))
    from shared_kernel.fingerprints import fingerprint_payload
    from subsystems.orders.historical_service_accounting_workflow import HistoricalAttributionPreview
    fingerprint = fingerprint_payload({"test": "partial-service"})
    candidate = HistoricalServiceFactsCorrectionCandidate(facts, (_completed_period(),), fingerprint)
    preview = HistoricalAttributionPreview(candidate, None, fingerprint, False,
                                          accounting_pending=plan.pending, volume_repricing=plan)
    financial_calls = []
    monkeypatch.setattr("infrastructure.mysql.pricing_configuration_repository.persist_historical_repricing",
                        lambda *args: financial_calls.append(args))

    class Cursor:
        lastrowid = 42

        def __init__(self):
            self.writes = []

        def execute(self, statement, parameters):
            self.writes.append((statement, parameters))

        def close(self):
            pass

    connection = _LoadConnection()
    connection.cursor_instance = Cursor()
    intent = HistoricalAttributionIntent(facts.case_no, ((3, 3),), "逐人服務證據", (_completed_period(),))
    receipt = MySqlHistoricalServiceAccountingRepository(connection).persist_attribution(
        intent, preview, fingerprint, actor=request.actor, reason=request.reason,
        key=request.idempotency_key, correlation=request.correlation_id)
    writes = connection.cursor_instance.writes
    snapshot = json.loads(writes[0][1][-1])
    assert len(financial_calls) == 1
    assert snapshot["comparison_baseline_event_id"] == 41
    assert snapshot["comparison_amounts_basis"] == "preserved_incomplete_attribution_baseline"
    assert snapshot["service_facts"] == [_completed_period().canonical_payload()]
    assert snapshot["accounting_pending"] == list(plan.pending)
    assert snapshot["financial_correction"]["persons"][0]["hours"] == "24"
    assert receipt.total_actual_service_days == 40
    assert writes[0][1][5:10] == (40, Decimal("360"), 4000, 99000, 108000)
    assert "SELECT %s,assignment_id" in writes[1][0]
    assert "THEN %s*actual_service_days" in writes[1][0]
    assert writes[1][1] == (42, 19, 3, Decimal("8"), 41)
    assert len(writes) == 3
    assert all("UPDATE historical_service_day_items" not in statement for statement, _ in writes)
    assert all("historical_service_accounting_outbox" not in statement for statement, _ in writes)
    assert all("UPDATE orders" not in statement and "case_staff_assignments" not in statement for statement, _ in writes)


def test_partial_completed_correction_replays_once_and_rejects_stale_without_writes():
    from shared_kernel.fingerprints import fingerprint_payload
    from subsystems.orders.historical_service_accounting_workflow import (
        HistoricalServiceAccountingReceipt, StoredHistoricalServiceAccountingReceipt,
    )
    facts, request = _partial_completed_facts()

    class Repository:
        stored = None
        writes = 0
        current = facts

        def load(self, case_no, *, for_update):
            return self.current

        def preview_service_volume(self, case_no, before, after, *, for_update):
            return HistoricalRepricingPlan(case_no, 2, 4, (), (),
                pending=("historical_pricing_total_service_hours_required",))

        def lock_attribution_order(self, case_no):
            pass

        def find_receipt(self, key):
            return self.stored

        def persist_attribution(self, intent, preview, command, **kwargs):
            self.writes += 1
            receipt = HistoricalServiceAccountingReceipt(facts.case_no, 2, 2, 4, 40, 99000, 108000,
                                                         preview.fingerprint, accounting_pending=preview.accounting_pending)
            self.stored = StoredHistoricalServiceAccountingReceipt(command, receipt)
            return receipt

    class Unit:
        commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def commit(self):
            self.commits += 1

    repository, unit = Repository(), Unit()
    workflow = HistoricalServiceAccountingWorkflow(repository, lambda: unit)
    intent = HistoricalAttributionIntent(facts.case_no, ((3, 3),), "逐人服務證據", (_completed_period(),))
    preview = workflow.preview_attribution(intent)
    kwargs = dict(actor=request.actor, reason=request.reason, key=request.idempotency_key, correlation=request.correlation_id)
    repository.current = replace(facts, lifecycle_version=facts.lifecycle_version + 1)
    with pytest.raises(ValueError, match="historical_attribution_preview_stale"):
        workflow.apply_attribution(intent, preview.fingerprint, **kwargs)
    assert repository.writes == unit.commits == 0
    repository.current = facts
    first = workflow.apply_attribution(intent, preview.fingerprint, **kwargs)
    replay = workflow.apply_attribution(intent, preview.fingerprint, **kwargs)
    assert first.accounting_pending == replay.accounting_pending
    assert replay.replayed
    assert repository.writes == unit.commits == 1
    with pytest.raises(ValueError, match="historical_attribution_idempotency_conflict"):
        workflow.apply_attribution(intent, fingerprint_payload({"test": "different-preview"}), **kwargs)
    assert repository.writes == 1
