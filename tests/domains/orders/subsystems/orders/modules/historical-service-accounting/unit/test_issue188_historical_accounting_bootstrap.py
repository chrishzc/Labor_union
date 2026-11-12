"""Historical comparisons read verified pricing and report missing sources."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from api.routes.historical_service_accounting import _call
from domains.orders.historical_service_accounting import HistoricalActualServiceDaysInput
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import PayrollPolicyKind, rate_snapshot
from infrastructure.mysql.historical_service_accounting_repository import (
    MySqlHistoricalServiceAccountingRepository,
)
from shared_kernel.identities import CorrelationId
from shared_kernel.money import MoneyNTD
from subsystems.orders.historical_service_accounting_workflow import (
    HistoricalServiceAccountingAssignmentFacts,
    HistoricalServiceAccountingFacts,
    ConfirmHistoricalServiceDaysIntent,
    HistoricalServiceAccountingWorkflow,
)


class _LoadCursor:
    def __init__(self, *, terms=True, rate=True, identity="一般市民", birth_count=None):
        self.terms = terms
        self.rate = rate
        self.identity = identity
        self.birth_count = birth_count
        self.statements = []
        self._one = None
        self._all = ()

    def execute(self, statement, parameters):
        normalized = " ".join(statement.split())
        self.statements.append((normalized, parameters))
        if "AS multi_birth_count FROM orders" in statement:
            self._one = {"identity_status": self.identity, "multi_birth_count": self.birth_count}
        elif "FROM payroll_rate_policies" in statement:
            rate = rate_snapshot("assignment:188", parameters[0], PayrollPolicyKind(parameters[1]))
            self._one = {"hourly_rate_ntd": rate.hourly_rate.amount}
        elif "FROM orders o JOIN clients c" in statement:
            self._one = {
                "case_no": "CASE-188",
                "status": OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value,
                "lifecycle_version": 7,
                "service_days": 30,
                "service_hours_per_day": 8,
                "floor_fee": 3_000,
                "identity_status": self.identity,
                "client_finance_version": 0,
                "payroll_version": 0,
                "adoption_receipt_id": 188,
                "source_event_identity": "historical-source:188",
                "historical_day_revision": 0,
                "client_policy_version": "client-policy:188" if self.terms else None,
                "client_hourly_rate_ntd": 280 if self.terms else None,
                "completed_on": date(2026, 4, 20),
                "staff_payment_due_date": None,
            }
        elif "FROM historical_order_pairing_evidence evidence" in statement:
            self._all = (
                {
                    "assignment_id": 188,
                    "staff_id": 18,
                    "staff_name": "月嫂乙",
                    "payroll_policy_version": "payroll-policy:188" if self.rate else None,
                    "payroll_policy_kind": PayrollPolicyKind.CITIZEN.value if self.rate else None,
                    "payroll_hourly_rate_ntd": 300 if self.rate else None,
                },
            )
        elif "FROM payroll_adjustment_allocations" in statement:
            self._all = ()

    def fetchone(self):
        value, self._one = self._one, None
        return value

    def fetchall(self):
        value, self._all = self._all, ()
        return value

    def close(self):
        return None


class _LoadConnection:
    def __init__(self, **facts):
        self.cursor_instance = _LoadCursor(**facts)

    def cursor(self):
        return self.cursor_instance


def test_missing_account_roots_project_as_zero_without_false_not_found():
    connection = _LoadConnection()

    facts = MySqlHistoricalServiceAccountingRepository(connection).load(
        "CASE-188", for_update=False
    )

    assert facts.client_finance_version == 0
    assert facts.payroll_version == 0
    root_statement = connection.cursor_instance.statements[0][0]
    assert "LEFT JOIN client_finance_accounts" in root_statement
    assert "LEFT JOIN payroll_case_accounts" in root_statement
    assert "COALESCE(client_account.aggregate_version,0)" in root_statement
    assert "COALESCE(payroll_account.aggregate_version,0)" in root_statement


def test_missing_client_payment_terms_fails_closed_with_specific_code():
    repository = MySqlHistoricalServiceAccountingRepository(_LoadConnection(terms=False))

    with pytest.raises(ValueError, match="historical_client_payment_terms_missing"):
        repository.load("CASE-188", for_update=False)


@pytest.mark.parametrize(("identity", "birth_count", "kind", "amount"), [
    ("一般市民", None, PayrollPolicyKind.CITIZEN, 300),
    ("低收入戶", None, PayrollPolicyKind.SUBSIDIZED_CITIZEN, 350),
    ("原住民", None, PayrollPolicyKind.SUBSIDIZED_CITIZEN, 350),
    ("非市民", None, PayrollPolicyKind.NON_CITIZEN, 320),
    ("非市民", "雙胞胎", PayrollPolicyKind.TWINS, 450),
])
def test_missing_payroll_snapshots_use_approved_default(identity, birth_count, kind, amount):
    connection = _LoadConnection(rate=False, identity=identity, birth_count=birth_count)
    facts = MySqlHistoricalServiceAccountingRepository(connection).load("CASE-188", for_update=False)
    snapshot = facts.assignments[0].rate_snapshot

    assert snapshot.policy_version == "approved-rates-v1"
    assert snapshot.policy_kind == kind
    assert snapshot.hourly_rate == MoneyNTD(amount)


@pytest.mark.parametrize(
    "code",
    [
        "historical_client_payment_terms_missing",
        "historical_payroll_rate_policy_missing",
    ],
)
def test_missing_canonical_policy_is_exposed_as_domain_blocker(code):
    def command():
        raise ValueError(code)

    with pytest.raises(HTTPException) as raised:
        _call(command, "unused", CorrelationId("issue-188"))

    assert raised.value.status_code == 409
    error = raised.value.detail["error"]
    assert error["category"] == "domain_blocked"
    assert error["code"] == code
    assert error["domain_blockers"] == [code]


def test_historical_service_accounting_facts_rejects_float_service_hours():
    with pytest.raises(TypeError, match="service hours per day must use Decimal or int"):
        HistoricalServiceAccountingFacts(
            case_no="CASE-188",
            lifecycle_status=OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
            lifecycle_version=1,
            adoption_receipt_id=1,
            adoption_source_identity="source:1",
            historical_day_revision=0,
            client_finance_version=0,
            payroll_version=0,
            contracted_service_days=10,
            service_hours_per_day=8.5,
            contractual_floor_fee=MoneyNTD(0),
            client_identity_status="一般市民",
            assignments=(
                HistoricalServiceAccountingAssignmentFacts(
                    "assignment:1",
                    1,
                    "月嫂甲",
                    rate_snapshot("assignment:1", "policy:1", PayrollPolicyKind.CITIZEN),
                    MoneyNTD(0),
                ),
            ),
            client_policy_version="policy:1",
            client_hourly_rate=MoneyNTD(280),
            completed_on=date(2026, 4, 20),
            staff_payment_due_date=None,
        )


def test_service_hours_per_day_loads_as_decimal_and_supports_manual_comparison():
    connection = _LoadConnection()
    repository = MySqlHistoricalServiceAccountingRepository(connection)
    workflow = HistoricalServiceAccountingWorkflow(repository, lambda: None)

    facts = workflow.query("CASE-188")
    assert isinstance(facts.service_hours_per_day, Decimal)
    assert facts.service_hours_per_day == Decimal("8")
    comparison = workflow.preview(ConfirmHistoricalServiceDaysIntent(
        "CASE-188", (HistoricalActualServiceDaysInput("assignment:188", 18, 26),),
    ))
    assert comparison.service_days.total_actual_service_days == 26
    assert all(statement.startswith("SELECT") for statement, _ in connection.cursor_instance.statements)
