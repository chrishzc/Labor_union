"""Focused regression coverage for issue #188 historical accounting bootstrap."""

import inspect

import pytest
from fastapi import HTTPException

from api.routes.historical_service_accounting import _call
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import PayrollPolicyKind
from infrastructure.mysql.historical_service_accounting_repository import (
    MySqlHistoricalServiceAccountingRepository,
    _ensure_accounting_accounts,
)
from shared_kernel.identities import CorrelationId


class _LoadCursor:
    def __init__(self, *, terms=True, rate=True):
        self.terms = terms
        self.rate = rate
        self.statements = []
        self._one = None
        self._all = ()

    def execute(self, statement, parameters):
        normalized = " ".join(statement.split())
        self.statements.append((normalized, parameters))
        if "FROM orders o JOIN clients c" in statement:
            self._one = {
                "case_no": "CASE-188",
                "status": OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value,
                "lifecycle_version": 7,
                "service_days": 30,
                "service_hours_per_day": 8,
                "floor_fee": 3_000,
                "identity_status": "一般市民",
                "client_finance_version": 0,
                "payroll_version": 0,
                "adoption_receipt_id": 188,
                "source_event_identity": "historical-source:188",
                "historical_day_revision": 0,
                "client_policy_version": "client-policy:188" if self.terms else None,
                "client_hourly_rate_ntd": 280 if self.terms else None,
            }
        elif "FROM historical_order_pairing_evidence evidence" in statement:
            self._all = (
                {
                    "assignment_id": 188,
                    "staff_id": 18,
                    "staff_name": "月嫂乙",
                    "payroll_policy_version": "payroll-policy:188" if self.rate else None,
                    "payroll_policy_kind": PayrollPolicyKind.CITIZEN.value if self.rate else None,
                    "payroll_hourly_rate_ntd": 320 if self.rate else None,
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
    def __init__(self, *, terms=True, rate=True):
        self.cursor_instance = _LoadCursor(terms=terms, rate=rate)

    def cursor(self):
        return self.cursor_instance


class _RecordingCursor:
    def __init__(self):
        self.statements = []

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))


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


def test_missing_payroll_rate_fails_closed_with_specific_code():
    repository = MySqlHistoricalServiceAccountingRepository(_LoadConnection(rate=False))

    with pytest.raises(ValueError, match="historical_payroll_rate_policy_missing"):
        repository.load("CASE-188", for_update=False)


def test_apply_bootstrap_only_creates_zero_version_account_roots():
    cursor = _RecordingCursor()

    _ensure_accounting_accounts(cursor, "CASE-188")

    assert cursor.statements == [
        (
            "INSERT INTO client_finance_accounts (case_no,aggregate_version) VALUES (%s,0) "
            "ON DUPLICATE KEY UPDATE case_no=VALUES(case_no)",
            ("CASE-188",),
        ),
        (
            "INSERT INTO payroll_case_accounts (case_no,aggregate_version) VALUES (%s,0) "
            "ON DUPLICATE KEY UPDATE case_no=VALUES(case_no)",
            ("CASE-188",),
        ),
    ]


def test_account_bootstrap_runs_before_historical_event_and_obligation_writes():
    source = inspect.getsource(MySqlHistoricalServiceAccountingRepository.persist)

    assert source.index("_ensure_accounting_accounts") < source.index(
        "INSERT INTO historical_service_day_events"
    )
    assert source.index("_ensure_accounting_accounts") < source.index(
        "_write_client_obligation"
    )
    assert source.index("_ensure_accounting_accounts") < source.index(
        "_write_staff_obligations"
    )


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
