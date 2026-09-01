"""Write-once persistence for historical service-day accounting."""

from dataclasses import replace

from domains.orders.historical_service_accounting import HistoricalActualServiceDaysInput
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import PayrollPolicyKind, rate_snapshot
from infrastructure.mysql.historical_service_accounting_repository import (
    MySqlHistoricalServiceAccountingRepository,
    _ensure_assignment_rate_snapshots,
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
    def __init__(self, *, client_amount=None, staff_amount=None):
        self.client_amount = client_amount
        self.staff_amount = staff_amount
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
    assert parameters[3] == 8_400
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
    assert parameters[3] == 0
    assert parameters[4] == "settled"


def test_existing_client_day_projection_is_rejected_without_difference_obligation():
    candidate, request = _candidate_and_request()
    cursor = _Cursor(client_amount=8_400)

    import pytest

    with pytest.raises(ValueError, match="historical_actual_service_days_already_confirmed"):
        _write_client_obligation(cursor, request, candidate, "source:event", 3)
    assert all(not statement.startswith("INSERT INTO") for statement, _ in cursor.statements)


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


def test_existing_staff_day_projection_is_rejected_without_recovery_obligation():
    candidate, request = _candidate_and_request()
    cursor = _Cursor(staff_amount=8_400)

    import pytest

    with pytest.raises(ValueError, match="historical_actual_service_days_already_confirmed"):
        _write_staff_obligations(cursor, request, candidate, "source:event", 5)
    assert all(not statement.startswith("INSERT INTO") for statement, _ in cursor.statements)


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
