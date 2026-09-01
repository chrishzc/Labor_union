"""Immutable difference-obligation persistence for historical accounting corrections."""

from domains.orders.historical_service_accounting import HistoricalActualServiceDaysInput
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import PayrollPolicyKind, rate_snapshot
from infrastructure.mysql.historical_service_accounting_repository import (
    MySqlHistoricalServiceAccountingRepository,
    _write_client_obligation,
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
    _candidate,
)


class _Cursor:
    def __init__(self, *, client_amount=None, staff_amount=None, staff_states=()):
        self.client_amount = client_amount
        self.staff_amount = staff_amount
        self.staff_states = staff_states
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
        elif "FROM staff_obligations obligation WHERE obligation.case_no" in statement:
            self._all = self.staff_states
        elif statement.startswith("SELECT obligation_identity"):
            self._one = None

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
        historical_day_revision=1,
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
    )
    intent = ConfirmHistoricalServiceDaysIntent(
        "CASE-19",
        (HistoricalActualServiceDaysInput("assignment:19", 3, 3),),
    )
    candidate = _candidate(facts, intent)
    request = ApplyHistoricalServiceAccounting(
        intent,
        3,
        1,
        2,
        4,
        candidate.fingerprint,
        IdempotencyKey("historical-days:19:revision:2"),
        ActorContext("operator"),
        "修正舊系統實際服務天數",
        CorrelationId("historical-days:19:revision:2"),
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
    assert any("JOIN assignment_payroll_rate_snapshots rate" in statement for statement in statements)
    assert any("FROM payroll_adjustment_allocations" in statement for statement in statements)
    assert all(statement.endswith("FOR UPDATE") for statement in statements)


def _insert_parameters(cursor, table):
    return next(
        parameters
        for statement, parameters in cursor.statements
        if statement.startswith(f"INSERT INTO {table} ")
    )


def _paid_staff_state():
    return ({
        "obligation_identity": "historical-service:CASE-19:revision:1:assignment:19:payable_to_staff",
        "assignment_id": 19,
        "obligation_kind": "service_pay",
        "direction": "payable_to_staff",
        "source_obligation_identity": None,
        "status": "open",
        "payout_history_exists": 1,
    },)


def _unpaid_staff_state():
    row = dict(_paid_staff_state()[0])
    row["payout_history_exists"] = 0
    return (row,)


def test_client_correction_appends_receivable_difference_without_overwriting_prior_obligation():
    candidate, request = _candidate_and_request()
    cursor = _Cursor(client_amount=5_600)

    _write_client_obligation(cursor, request, candidate, "source:event", 3)

    parameters = _insert_parameters(cursor, "client_obligation_events")
    assert parameters[2] == "receivable_from_client"
    assert parameters[3] == 2_800
    assert all(not statement.startswith("UPDATE client_obligations") for statement, _ in cursor.statements)


def test_client_downward_correction_appends_refund_difference():
    candidate, request = _candidate_and_request()
    cursor = _Cursor(client_amount=11_200)

    _write_client_obligation(cursor, request, candidate, "source:event", 3)

    parameters = _insert_parameters(cursor, "client_obligation_events")
    assert parameters[2] == "payable_to_client"
    assert parameters[3] == 2_800


def test_staff_downward_correction_appends_recovery_difference_without_overwriting_prior_obligation():
    candidate, request = _candidate_and_request()
    cursor = _Cursor(staff_amount=11_200, staff_states=_paid_staff_state())

    _write_staff_obligations(cursor, request, candidate, "source:event", 5)

    parameters = _insert_parameters(cursor, "staff_obligation_events")
    assert parameters[4] == "reversal"
    assert parameters[5] == "receivable_from_staff"
    assert parameters[6] == _paid_staff_state()[0]["obligation_identity"]
    assert parameters[7] == "reversal"
    assert parameters[8] == 2_800
    assert all(not statement.startswith("UPDATE staff_obligations") for statement, _ in cursor.statements)


def test_unpaid_staff_correction_rebuilds_existing_obligation_in_place():
    candidate, request = _candidate_and_request()
    cursor = _Cursor(staff_amount=5_600, staff_states=_unpaid_staff_state())

    _write_staff_obligations(cursor, request, candidate, "source:event", 5)

    parameters = _insert_parameters(cursor, "staff_obligation_events")
    assert parameters[0] == _unpaid_staff_state()[0]["obligation_identity"]
    assert parameters[6] == 5_600
    assert parameters[7] == 8_400
    assert any(
        statement.startswith("UPDATE staff_obligations SET amount_due_ntd=")
        for statement, _ in cursor.statements
    )
    assert all(
        not statement.startswith("INSERT INTO staff_obligations")
        for statement, _ in cursor.statements
    )


def test_paid_staff_increase_appends_source_bound_adjustment():
    candidate, request = _candidate_and_request()
    cursor = _Cursor(staff_amount=5_600, staff_states=_paid_staff_state())

    _write_staff_obligations(cursor, request, candidate, "source:event", 5)

    parameters = _insert_parameters(cursor, "staff_obligation_events")
    assert parameters[4] == "adjustment"
    assert parameters[5] == "payable_to_staff"
    assert parameters[6] == _paid_staff_state()[0]["obligation_identity"]
    assert parameters[7] == "adjustment"
    assert parameters[8] == 2_800


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


def test_unchanged_totals_do_not_create_difference_obligations():
    candidate, request = _candidate_and_request()
    cursor = _Cursor(client_amount=8_400, staff_amount=8_400)

    _write_client_obligation(cursor, request, candidate, "source:event", 3)
    _write_staff_obligations(cursor, request, candidate, "source:event", 5)

    assert all(not statement.startswith("INSERT INTO") for statement, _ in cursor.statements)
