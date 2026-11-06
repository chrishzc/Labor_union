"""Read and snapshot persistence for historical service-day comparisons."""

from datetime import date

from domains.orders.historical_service_accounting import HistoricalActualServiceDaysInput
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
    _candidate,
)


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
