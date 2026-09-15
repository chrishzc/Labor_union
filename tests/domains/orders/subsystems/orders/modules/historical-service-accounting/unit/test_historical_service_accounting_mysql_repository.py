"""Write-once persistence for historical service-day accounting."""

from dataclasses import replace
from datetime import date

from domains.orders.historical_service_accounting import HistoricalActualServiceDaysInput
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import PayrollPolicyKind, rate_snapshot
from infrastructure.mysql.historical_service_accounting_repository import (
    MySqlHistoricalServiceAccountingRepository,
    _ensure_assignment_rate_snapshots,
    _write_client_obligation,
    _write_order_staff_payment_due_date,
    _write_payroll_outbox,
    _write_staff_obligations,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.orders.historical_service_accounting_workflow import (
    ApplyHistoricalServiceAccounting,
    ConfirmHistoricalServiceDaysIntent,
    HistoricalServiceAccountingAssignmentFacts,
    HistoricalServiceAccountingFacts,
    HistoricalServiceAccountingReceipt,
    HistoricalServiceAccountingWorkflow,
    _candidate,
)


class _Cursor:
    def __init__(self, *, client_amount=None, staff_amount=None, payout_history_exists=None):
        self.client_amount = client_amount
        self.staff_amount = staff_amount
        self.payout_history_exists = payout_history_exists
        self.statements = []
        self.lastrowid = 41
        self.rowcount = 1
        self._one = None
        self._all = ()

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))
        if "FROM historical_service_day_projections projection" in statement:
            if "client_obligation_amount_ntd" in statement:
                self._one = (
                    None
                    if self.client_amount is None
                    else {"client_obligation_amount_ntd": self.client_amount}
                )
            else:
                self._all = (
                    ()
                    if self.staff_amount is None
                    else (
                        {
                            "assignment_id": 19,
                            "staff_obligation_amount_ntd": self.staff_amount,
                        },
                    )
                )
        elif statement.startswith("SELECT obligation_identity,payout_history_exists"):
            self._one = (
                None
                if self.payout_history_exists is None
                else {
                    "obligation_identity": parameters[0],
                    "payout_history_exists": self.payout_history_exists,
                }
            )
        elif statement.startswith("SELECT obligation_identity"):
            self._one = None

    def executemany(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))

    def fetchone(self):
        value, self._one = self._one, None
        return value

    def fetchall(self):
        value, self._all = self._all, ()
        return value


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


def test_apply_freezes_projected_case_rate_for_legacy_assignment() -> None:
    candidate, _ = _candidate_and_request()
    cursor = _Cursor()

    _ensure_assignment_rate_snapshots(cursor, candidate)

    statement, parameters = next(
        item
        for item in cursor.statements
        if item[0].startswith("INSERT INTO assignment_payroll_rate_snapshots ")
    )
    assert "source_identity_status" in statement
    assert parameters == (
        (19, "policy:1", PayrollPolicyKind.CITIZEN.value, 300, "一般市民"),
    )


def _insert_parameters(cursor, table):
    return next(
        parameters
        for statement, parameters in cursor.statements
        if statement.startswith(f"INSERT INTO {table} ")
    )


def test_initial_client_obligation_is_established_once():
    candidate, request = _candidate_and_request()
    cursor = _Cursor()

    _write_client_obligation(cursor, request, candidate, "source:event", 3)

    parameters = _insert_parameters(cursor, "client_obligation_events")
    assert parameters[2] == "receivable_from_client"
    assert parameters[3] == "established"
    assert parameters[4] == 8_400
    assert all(not statement.startswith("UPDATE client_obligations") for statement, _ in cursor.statements)


def test_zero_client_obligation_is_immediately_settled_without_payment() -> None:
    candidate, request = _candidate_and_request()
    candidate = replace(
        candidate,
        client_finance=replace(
            candidate.client_finance,
            service_receivable=MoneyNTD(0),
            total_receivable=MoneyNTD(0),
        ),
    )
    cursor = _Cursor()

    _write_client_obligation(cursor, request, candidate, "source:event", 3)

    statement, parameters = next(
        item
        for item in cursor.statements
        if item[0].startswith("INSERT INTO client_obligations ")
    )
    assert parameters[4] == 0
    assert parameters[5] == "settled"


def test_client_day_revision_creates_a_source_bound_difference_obligation():
    candidate, request = _candidate_and_request()
    candidate = replace(candidate, facts=replace(candidate.facts, historical_day_revision=1))
    cursor = _Cursor(client_amount=10_000)

    _write_client_obligation(cursor, request, candidate, "source:event", 3)

    event_parameters = _insert_parameters(cursor, "client_obligation_events")
    assert event_parameters[2] == "payable_to_client"
    assert event_parameters[3] == "reversed"
    assert event_parameters[4] == 1_600
    assert event_parameters[6] == (
        "historical-service:CASE-19:revision:1:client:receivable_from_client"
    )


def test_initial_staff_obligation_is_payable_and_established_once():
    candidate, request = _candidate_and_request()
    cursor = _Cursor()

    _write_staff_obligations(cursor, request, candidate, "source:event", 5)

    parameters = _insert_parameters(cursor, "staff_obligation_events")
    assert parameters[4] == "service_pay"
    assert parameters[5] == "payable_to_staff"
    assert parameters[6] is None
    assert parameters[7] == "established"
    assert parameters[8] == 8_400
    assert parameters[9] == date(2026, 5, 15)

    obligation_parameters = _insert_parameters(cursor, "staff_obligations")
    assert obligation_parameters[8] == date(2026, 5, 15)


def test_historical_full_subsidy_staff_due_date_is_second_month_after_completion():
    candidate, request = _candidate_and_request()
    candidate = _candidate(
        replace(
            candidate.facts,
            client_identity_status="補助市民",
            contractual_floor_fee=MoneyNTD(0),
        ),
        request.intent,
    )

    assert candidate.client_finance.total_receivable == MoneyNTD(0)
    assert candidate.staff_payment_due_date == date(2026, 6, 15)


def test_historical_accounting_sets_the_orders_payment_due_date_root_fact():
    candidate, _ = _candidate_and_request()
    cursor = _Cursor()

    _write_order_staff_payment_due_date(cursor, candidate)

    statement, parameters = cursor.statements[-1]
    assert statement.startswith("UPDATE orders SET staff_payment_due_date=%s")
    assert parameters == (date(2026, 5, 15), "CASE-19")


def test_historical_accounting_preserves_an_existing_orders_payment_due_date():
    candidate, request = _candidate_and_request()
    candidate = _candidate(
        replace(candidate.facts, staff_payment_due_date=date(2026, 5, 15)),
        request.intent,
    )
    cursor = _Cursor()

    _write_order_staff_payment_due_date(cursor, candidate)

    assert cursor.statements == []


def test_default_accounting_uses_the_orders_recorded_service_days_without_manual_input():
    candidate, _ = _candidate_and_request()

    class Repository:
        def __init__(self):
            self.persisted = None

        def load(self, case_no, *, for_update):
            assert case_no == "CASE-19"
            assert for_update is True
            return candidate.facts

        def find_receipt(self, key):
            return None

        def persist(self, request, persisted_candidate):
            self.persisted = persisted_candidate
            return HistoricalServiceAccountingReceipt(
                "CASE-19", 1, 3, 5,
                persisted_candidate.service_days.total_actual_service_days,
                persisted_candidate.client_finance.total_receivable.amount,
                persisted_candidate.payroll.total_payable.amount,
                persisted_candidate.fingerprint,
            )

    repository = Repository()
    workflow = HistoricalServiceAccountingWorkflow(repository, lambda: None)

    workflow.establish_default_in_current_unit_of_work(
        case_no="CASE-19",
        source_identity="historical-source:19",
        actor="operator",
        correlation_id="historical-default:19",
    )

    assert repository.persisted.service_days.total_actual_service_days == 40
    assert repository.persisted.payroll.assignments[0].actual_service_days == 40
    assert repository.persisted.staff_payment_due_date == date(2026, 5, 15)


def test_unpaid_staff_obligation_is_rebuilt_when_actual_days_are_revised():
    candidate, request = _candidate_and_request()
    candidate = replace(candidate, facts=replace(candidate.facts, historical_day_revision=1))
    cursor = _Cursor(staff_amount=9_000, payout_history_exists=False)

    _write_staff_obligations(cursor, request, candidate, "source:event", 5)

    event_parameters = _insert_parameters(cursor, "staff_obligation_events")
    assert event_parameters[4:6] == (9_000, 8_400)
    update = next(
        item for item in cursor.statements if item[0].startswith("UPDATE staff_obligations SET")
    )
    assert update[1][0] == 8_400


def test_paid_staff_obligation_gets_a_source_bound_reversal_for_the_difference():
    candidate, request = _candidate_and_request()
    candidate = replace(candidate, facts=replace(candidate.facts, historical_day_revision=1))
    cursor = _Cursor(staff_amount=9_000, payout_history_exists=True)

    _write_staff_obligations(cursor, request, candidate, "source:event", 5)

    event_parameters = _insert_parameters(cursor, "staff_obligation_events")
    assert event_parameters[4] == "reversal"
    assert event_parameters[5] == "receivable_from_staff"
    assert event_parameters[6] == (
        "historical-service:CASE-19:revision:1:assignment:19:payable_to_staff"
    )
    assert event_parameters[8] == 600
    assert all(
        not statement.startswith("UPDATE staff_obligations SET")
        for statement, _ in cursor.statements
    )


def test_paid_staff_obligation_gets_an_adjustment_when_revised_pay_is_higher():
    candidate, request = _candidate_and_request()
    candidate = replace(candidate, facts=replace(candidate.facts, historical_day_revision=1))
    cursor = _Cursor(staff_amount=7_000, payout_history_exists=True)

    _write_staff_obligations(cursor, request, candidate, "source:event", 5)

    event_parameters = _insert_parameters(cursor, "staff_obligation_events")
    assert event_parameters[4] == "adjustment"
    assert event_parameters[5] == "payable_to_staff"
    assert event_parameters[8] == 1_400


def test_payroll_change_uses_existing_payroll_outbox_contract():
    candidate, request = _candidate_and_request()
    cursor = _Cursor()

    _write_payroll_outbox(cursor, request, candidate, 5)

    statement, parameters = next(
        item for item in cursor.statements if item[0].startswith("INSERT INTO payroll_outbox")
    )
    assert "'staff_obligation_changed'" in statement
    assert parameters[0] == "CASE-19"
    assert parameters[1].endswith(":payroll-outbox")
    assert '"payroll_version":5' in parameters[2]
    assert '"total_payable_ntd":8400' in parameters[2]
