"""Unit coverage for the cancellation read model's staff-lock boundary."""

from __future__ import annotations

import pytest

from infrastructure.mysql import order_cancellation_read_model as read_model
from infrastructure.mysql import historical_unserved_correction_read_model as historical_read_model


class StaffLockCursor:
    def __init__(self, result_sets):
        self._result_sets = list(result_sets)
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))

    def fetchall(self):
        return self._result_sets.pop(0)


def test_cancellation_locks_all_impacted_staff_before_requested_staff_validation():
    cursor = StaffLockCursor([[{"id": 1}, {"id": 2}], [{"id": 2}]])

    read_model._lock_staff(cursor, (1, 2), requested_staff_ids=(2,))

    mutex_statement, mutex_parameters = cursor.calls[0]
    active_statement, active_parameters = cursor.calls[1]
    assert "ORDER BY id FOR UPDATE" in mutex_statement
    assert mutex_parameters == (1, 2)
    assert "status='active'" in active_statement
    assert "FOR UPDATE" not in active_statement
    assert active_parameters == (2,)


def test_cancellation_rejects_inactive_requested_staff_after_mutex_lock():
    cursor = StaffLockCursor([[{"id": 1}, {"id": 2}], []])

    with pytest.raises(ValueError, match="scheduling_staff_not_found"):
        read_model._lock_staff(cursor, (1, 2), requested_staff_ids=(2,))

    assert "ORDER BY id FOR UPDATE" in cursor.calls[0][0]
    assert "status='active'" in cursor.calls[1][0]
    assert cursor.calls[1][1] == (2,)


def test_cancellation_without_impacted_staff_skips_staff_mutex():
    cursor = StaffLockCursor([])

    read_model._lock_staff(cursor, (), requested_staff_ids=())

    assert cursor.calls == []


class PresenceCursor:
    def __init__(self, present):
        self.present = set(present)
        self.table = None
        self.calls = []

    def execute(self, statement, parameters):
        import re
        self.table = re.search(r"FROM ([a-z_]+)", statement).group(1)
        self.calls.append(statement)

    def fetchone(self):
        return {"case_no": "CASE-1"} if self.table in self.present else None


def test_unassigned_date_only_cancellation_reads_without_financial_bootstrap(monkeypatch):
    from datetime import date, time
    from types import SimpleNamespace
    from domains.orders.terms import OrderTerms, ServiceTimeTerms
    from domains.orders.lifecycle import OrderEstablishmentEvidence, OrderLifecycleRootFacts, OrderLifecycleStatus
    from shared_kernel.money import MoneyNTD
    terms = OrderTerms(date(2026, 8, 1), 25, 8, MoneyNTD(0), ServiceTimeTerms(time(8), time(16), 0))
    monkeypatch.setattr(read_model, "_order_facts", lambda _: SimpleNamespace(version=3, terms=terms, service_data_locked=False))
    lifecycle = OrderLifecycleRootFacts("CASE-1", OrderLifecycleStatus.ESTABLISHED, False, date(2026, 8, 1), False, False, False)
    monkeypatch.setattr(read_model, "_load_lifecycle", lambda *_: lifecycle)
    monkeypatch.setattr(read_model, "load_order_establishment_evidence", lambda *_, **__: OrderEstablishmentEvidence(current_owner_status=OrderLifecycleStatus.ESTABLISHED))
    monkeypatch.setattr(historical_read_model, "load_historical_unserved_evidence", lambda *_, **__: None)
    cursor = PresenceCursor(())
    facts = read_model._assemble_cancellation_facts(cursor, {"case_no": "CASE-1", "status": "訂單成立", "actual_end_date": None}, None, lock=True, historical_origin=False)
    assert facts.order.actual_start_date == date(2026, 8, 1)
    assert facts.order.service_started is False
    assert facts.client_finance is None and facts.payroll is None
    assert facts.scheduling.aggregate_version is None
    assert all("FOR UPDATE" in call for call in cursor.calls)


@pytest.mark.parametrize("present, code", [
    (("client_finance_accounts",), "invalid_client_finance_facts"),
    (("client_payment_terms",), "invalid_client_finance_facts"),
    (("client_ledger_entries",), "invalid_client_finance_facts"),
    (("payroll_case_accounts",), "invalid_payroll_facts"),
    (("case_payroll_rate_policy_snapshots",), "invalid_payroll_facts"),
    (("staff_obligation_events",), "invalid_payroll_facts"),
])
def test_cancellation_absence_does_not_hide_partial_roots_or_financial_history(present, code):
    with pytest.raises(ValueError, match=code):
        read_model._validate_cancellation_owner_presence(PresenceCursor(present), "CASE-1", True)


@pytest.mark.parametrize("historical_origin", [False, True])
def test_zero_service_locked_read_keeps_retired_assignment_staff_locked_without_reselecting(monkeypatch, historical_origin):
    """Both normal and historical zero-service removal use old staff only for locking."""
    cursor = StaffLockCursor([[{"id": 1}, {"id": 2}]])
    expected = object()
    monkeypatch.setattr(read_model, "select_order", lambda *_, **__: {"case_no": "CASE-1"})
    monkeypatch.setattr(read_model, "_select_cancellation_aggregate", lambda *_, **__: None)
    monkeypatch.setattr(read_model, "_historical_cancellation_origin", lambda *_: historical_origin)
    monkeypatch.setattr(read_model, "_assemble_cancellation_facts", lambda *_, **__: expected)

    assert read_model.load_cancellation_locked_facts(cursor, "CASE-1", (1, 2), ()) is expected

    assert len(cursor.calls) == 1
    assert "ORDER BY id FOR UPDATE" in cursor.calls[0][0]
    assert "status='active'" not in cursor.calls[0][0]
    assert cursor.calls[0][1] == (1, 2)


def test_zero_service_still_rejects_a_missing_impacted_staff_mutex_row():
    cursor = StaffLockCursor([[{"id": 1}]])

    with pytest.raises(ValueError, match="cannot lock all requested staff"):
        read_model._lock_staff(cursor, (1, 2), requested_staff_ids=())


def test_requested_staff_cannot_be_validated_outside_the_impacted_mutex_set():
    cursor = StaffLockCursor([])

    with pytest.raises(ValueError, match="included in impacted staff locks"):
        read_model._lock_staff(cursor, (1,), requested_staff_ids=(2,))

    assert cursor.calls == []


@pytest.mark.parametrize("status, has_correction", [
    ("訂單取消", False),
    ("成立後未服務", True),
])
def test_operator_correction_readback_does_not_require_import_or_pairing_receipts(
    monkeypatch, status, has_correction,
):
    from domains.orders.historical_unserved_correction import historical_unserved_review_codes
    from domains.orders.lifecycle import OrderEstablishmentEvidence, OrderLifecycleStatus

    class Cursor(StaffLockCursor):
        def fetchone(self):
            assert "historical_unserved_correction.confirmed_established" in self.calls[-1][0]
            return {"id": 31}

    cursor = Cursor([[], [], [{"id": 15, "staff_id": 9}]])
    status_value = OrderLifecycleStatus(status)
    proof = OrderEstablishmentEvidence((31,) if has_correction else (), current_owner_status=status_value)
    monkeypatch.setattr(historical_read_model, "load_order_establishment_evidence", lambda *_, **__: proof)
    monkeypatch.setattr(historical_read_model, "_actual_service_evidence", lambda *_: ())
    monkeypatch.setattr(historical_read_model, "_prior_settlement", lambda *_: (None, ()))
    monkeypatch.setattr(historical_read_model, "_invalid_cash_reversal", lambda *_: False)
    monkeypatch.setattr(historical_read_model, "_cash_evidence_requires_review", lambda *_: True)

    evidence = historical_read_model.load_historical_unserved_evidence(cursor, "CASE-1", status, lock=True)
    assert evidence.historical_adoption_ids == evidence.historical_absence_event_ids == ()
    assert evidence.standalone_assignment_ids == (15,)
    assert evidence.standalone_staff_ids == (9,)
    assert "historical_unserved_cash_evidence_requires_review" in historical_unserved_review_codes(evidence)
    statements = [sql for sql, _ in cursor.calls]
    assert all("FOR UPDATE" in sql for sql in statements)
    assert any("confirmed_established" in sql for sql in statements) == has_correction
    assert "generation_id IS NULL" in statements[-1]
    assert "case_no=%s" in statements[-1]
    assert "pairing_evidence" not in statements[-1]


def test_net_client_cash_uses_refund_returns_and_gross_settlement_principal():
    from infrastructure.mysql.client_payments_query_repository import query_case_net_cash

    class Cursor(StaffLockCursor):
        def fetchone(self):
            return {"amount": 500}

    cursor = Cursor([])
    assert query_case_net_cash(cursor, "CASE-1") == 500
    ((sql, parameters),) = cursor.calls
    assert parameters == ("CASE-1",)
    assert "entry.entry_type IN ('reversal','refund_reversal')" in sql
    assert "original.case_no=entry.case_no" in sql
    assert "GREATEST(entry.amount_ntd" in sql
    assert "allocation.ledger_entry_id=entry.id" in sql


@pytest.fixture
def cancellation_without_assignment_rate(monkeypatch, request):
    from datetime import date, datetime, time
    from types import SimpleNamespace

    from api.dependencies.order_cancellation import OrderCancellationApplication
    from domains.client_finance.obligation_planning import ClientFinanceTermsSourceFacts, ClientPaymentTerms
    from domains.orders.cancellation import CancellationAssignmentFacts
    from domains.orders.historical_unserved_correction import HistoricalUnservedEvidence
    from domains.orders.lifecycle import OrderEstablishmentEvidence, OrderLifecycleRootFacts, OrderLifecycleStatus
    from domains.orders.terms import OrderTerms, ServiceTimeTerms
    from infrastructure.mysql import order_terms_read_model as terms_read_model
    from infrastructure.mysql import pricing_configuration_repository as pricing
    from infrastructure.mysql.order_cancellation_repository import MySqlOrderCancellationRepository
    from shared_kernel.clock import FixedBusinessClock
    from shared_kernel.money import MoneyNTD
    from subsystems.orders.cancellation_workflow import OrderCancellationWorkflow

    has_assignment, status_value = getattr(request, "param", (True, "訂單取消"))
    case_no = "CASE-1"
    start = date(2026, 8, 1)
    status = OrderLifecycleStatus(status_value)
    order_row = {
        "case_no": case_no, "status": status.value, "actual_start_date": None,
        "actual_end_date": None, "staff_payment_due_date": None,
    }
    terms = OrderTerms(start, 2, 8, MoneyNTD(1000), ServiceTimeTerms(time(8), time(17), 0))
    establishment = OrderEstablishmentEvidence(
        (31,) if status is OrderLifecycleStatus.ESTABLISHED_UNSERVED else (),
        current_owner_status=status,
    )
    finance = ClientFinanceTermsSourceFacts(
        case_no, 5, ClientPaymentTerms(0, MoneyNTD(100), start, start, None), (), (),
    )
    obligation = {
        "obligation_identity": "payable:11", "assignment_id": 11, "staff_id": 7,
        "obligation_kind": "service_pay", "direction": "payable_to_staff", "contracted_amount_ntd": 800,
        "amount_due_ntd": 800, "paid_net_amount_ntd": 0, "payout_history_exists": False, "due_date": None,
    }

    present = {"client_finance_accounts", "client_payment_terms", "payroll_case_accounts"}
    if has_assignment:
        present.add("case_payroll_rate_policy_snapshots")

    class Cursor(PresenceCursor):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def fetchone(self):
            if self.table in self.present:
                if self.table == "payroll_case_accounts":
                    return {"case_no": case_no, "aggregate_version": 3}
                if self.table == "case_payroll_rate_policy_snapshots":
                    return {"case_no": case_no, "policy_version": "policy-v1", "policy_kind": "citizen"}
            return super().fetchone()

        def fetchall(self):
            if self.table == "staff":
                return [{"id": 7}]
            assert self.table == "staff_overpayment_recoveries"
            return []

    monkeypatch.setattr(read_model, "select_order", lambda *_, **__: order_row)
    monkeypatch.setattr(read_model, "_historical_cancellation_origin", lambda *_: True)
    monkeypatch.setattr(read_model, "_require_selectable_staff", lambda *_, **__: None)
    aggregate = {"aggregate_version": 2} if has_assignment else None
    assignment_rows = ({"id": 11, "staff_id": 7},) if has_assignment else ()
    monkeypatch.setattr(read_model, "_select_cancellation_aggregate", lambda *_, **__: aggregate)
    monkeypatch.setattr(read_model, "_select_generation", lambda *_: {"generation_number": 1})
    monkeypatch.setattr(read_model, "_select_assignments", lambda *_: assignment_rows)
    monkeypatch.setattr(read_model, "_select_schedules", lambda *_: ())
    monkeypatch.setattr(read_model, "_lock_dated_occupancy", lambda *_: None)
    monkeypatch.setattr(read_model, "_load_cancellation_assignments", lambda *_, **__: (
        CancellationAssignmentFacts(11, 7, 1, (start,)),
    ))
    monkeypatch.setattr(historical_read_model, "load_historical_unserved_evidence", lambda *_, **__: (
        HistoricalUnservedEvidence(establishment, (), (), (), None)
    ))
    monkeypatch.setattr(read_model, "_load_client_finance", lambda *_: finance)
    monkeypatch.setattr(read_model, "query_case_net_cash", lambda *_: 0)
    monkeypatch.setattr(read_model, "_load_lifecycle", lambda *_: (
        OrderLifecycleRootFacts(case_no, status, False, None, False, True, False)
    ))
    monkeypatch.setattr(read_model, "load_order_establishment_evidence", lambda *_, **__: establishment)
    monkeypatch.setattr(read_model, "_order_facts", lambda _: SimpleNamespace(
        version=4, terms=terms, service_data_locked=False,
    ))
    monkeypatch.setattr(terms_read_model, "_select_payroll_assignment_ancestry", lambda *_: {})
    monkeypatch.setattr(terms_read_model, "_select_assignment_rates", lambda *_: ())
    monkeypatch.setattr(terms_read_model, "_select_payroll_adjustments", lambda *_: {})
    monkeypatch.setattr(terms_read_model, "_select_staff_obligations", lambda *_: (obligation,))
    monkeypatch.setattr(terms_read_model, "load_explicit_case_service_rate", lambda *_, **__: None)
    monkeypatch.setattr(pricing, "load_case_pricing", lambda *_, **__: None)
    repository = MySqlOrderCancellationRepository(SimpleNamespace(cursor=lambda: Cursor(present)))
    monkeypatch.setattr(repository, "list_caregiver_options", lambda _: ())
    workflow = OrderCancellationWorkflow(
        repository, lambda: pytest.fail("Preview must not open a write unit of work"),
        FixedBusinessClock(datetime(2026, 8, 2, 9).astimezone()),
    )
    return OrderCancellationApplication(repository, workflow), obligation


@pytest.mark.parametrize(
    "cancellation_without_assignment_rate", [(True, "訂單取消"), (False, "訂單取消")],
    indirect=True, ids=["missing-assignment-rate", "missing-case-rate-without-effective-assignment"],
)
def test_historical_unserved_query_and_preview_work_without_assignment_rate(cancellation_without_assignment_rate):
    from domains.orders.historical_unserved_correction import HistoricalUnservedCorrectionIntent

    application, _ = cancellation_without_assignment_rate
    query = application.query("CASE-1")
    assert query.facts.payroll.payroll_version == 3
    assert query.facts.payroll.source_terms == ()
    assert query.facts.payroll.existing_obligations[0].obligation_identity == "payable:11"

    preview = application.preview("CASE-1", (), historical_correction=HistoricalUnservedCorrectionIntent())
    assert preview.candidate.official_service_day_count == 0
    assert preview.payroll_impact.carried_rate_snapshots == ()
    assert tuple(
        (action.action.value, action.obligation_identity, action.amount.amount)
        for action in preview.payroll_impact.actions
    ) == (("close_unpaid", "payable:11", 800),)

    locked = application.repository.load_for_apply("CASE-1", (7,), (), allow_missing_payroll_rates=True)
    assert locked.payroll == query.facts.payroll


@pytest.mark.parametrize("cancellation_without_assignment_rate", [(False, "成立後未服務")], indirect=True)
def test_corrected_historical_unserved_query_without_case_rate_preserves_status_rejection(
    cancellation_without_assignment_rate,
):
    from domains.orders.historical_unserved_correction import HistoricalUnservedCorrectionIntent
    from domains.orders.lifecycle import OrderLifecycleStatus
    from shared_kernel.errors import ErrorCategory
    from subsystems.orders.cancellation_workflow import CancellationWorkflowError

    application, _ = cancellation_without_assignment_rate
    query = application.query("CASE-1")
    assert query.facts.lifecycle.current_status is OrderLifecycleStatus.ESTABLISHED_UNSERVED
    assert query.facts.payroll.payroll_version == 3
    assert query.facts.payroll.source_terms == ()

    with pytest.raises(CancellationWorkflowError) as error:
        application.preview("CASE-1", (), historical_correction=HistoricalUnservedCorrectionIntent())
    assert error.value.error.category is ErrorCategory.DOMAIN_BLOCKED
    assert error.value.error.code == "historical_unserved_status_ineligible"


def test_standard_cancellation_still_requires_assignment_rate(cancellation_without_assignment_rate):
    from datetime import date

    from domains.orders.cancellation import ConfirmedServiceDay

    application, _ = cancellation_without_assignment_rate
    with pytest.raises(ValueError, match="payroll_rate_policy_not_found"):
        application.preview("CASE-1", (ConfirmedServiceDay(date(2026, 8, 1), 7),))
    with pytest.raises(ValueError, match="payroll_rate_policy_not_found"):
        application.repository.load_for_apply("CASE-1", (7,), (7,))


def test_historical_unserved_retains_payroll_money_validation(cancellation_without_assignment_rate):
    from domains.orders.historical_unserved_correction import HistoricalUnservedCorrectionIntent

    application, obligation = cancellation_without_assignment_rate
    obligation["amount_due_ntd"] = "800.5"
    with pytest.raises(ValueError, match="non_integer_order_money"):
        application.preview("CASE-1", (), historical_correction=HistoricalUnservedCorrectionIntent())


@pytest.mark.parametrize("table", ["case_payroll_rate_policy_snapshots", "staff_obligations", "staff_obligation_events"])
def test_historical_unserved_still_rejects_payroll_facts_without_owner(table):
    with pytest.raises(ValueError, match="invalid_payroll_facts"):
        read_model._validate_cancellation_owner_presence(
            PresenceCursor((table,)), "CASE-1", True, allow_missing_payroll_rates=True,
        )
