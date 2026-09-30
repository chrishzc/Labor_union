"""Unit coverage for the cancellation read model's staff-lock boundary."""

from __future__ import annotations

import pytest

from infrastructure.mysql import order_cancellation_read_model as read_model


class StaffLockCursor:
    def __init__(self, result_sets):
        self._result_sets = list(result_sets)
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))

    def fetchall(self):
        return self._result_sets.pop(0)


def test_cancellation_locks_canonical_mutex_before_active_staff_validation():
    cursor = StaffLockCursor([[{"id": 1}, {"id": 2}], [{"id": 1}, {"id": 2}]])

    read_model._lock_staff(cursor, (1, 2))

    mutex_statement, mutex_parameters = cursor.calls[0]
    active_statement, active_parameters = cursor.calls[1]
    assert "ORDER BY id FOR UPDATE" in mutex_statement
    assert mutex_parameters == (1, 2)
    assert "status='active'" in active_statement
    assert "FOR UPDATE" not in active_statement
    assert active_parameters == (1, 2)


def test_cancellation_rejects_inactive_staff_after_mutex_lock():
    cursor = StaffLockCursor([[{"id": 1}, {"id": 2}], [{"id": 1}]])

    with pytest.raises(ValueError, match="scheduling_staff_not_found"):
        read_model._lock_staff(cursor, (1, 2))


def test_cancellation_without_impacted_staff_skips_staff_mutex():
    cursor = StaffLockCursor([])

    read_model._lock_staff(cursor, ())

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
    from domains.orders.lifecycle import OrderLifecycleRootFacts, OrderLifecycleStatus
    from shared_kernel.money import MoneyNTD
    terms = OrderTerms(date(2026, 8, 1), 25, 8, MoneyNTD(0), ServiceTimeTerms(time(8), time(16), 0))
    monkeypatch.setattr(read_model, "_order_facts", lambda _: SimpleNamespace(version=3, terms=terms, service_data_locked=False))
    lifecycle = OrderLifecycleRootFacts("CASE-1", OrderLifecycleStatus.ESTABLISHED, False, date(2026, 8, 1), False, False, False)
    monkeypatch.setattr(read_model, "_load_lifecycle", lambda *_: lifecycle)
    cursor = PresenceCursor(())
    facts = read_model._assemble_cancellation_facts(cursor, {"case_no": "CASE-1"}, None, lock=True, historical_origin=False)
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
