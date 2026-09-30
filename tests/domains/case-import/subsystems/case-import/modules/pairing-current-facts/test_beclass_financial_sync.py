"""BeClass rate correction coordinates Client Finance in the same transaction."""

from datetime import date
from types import SimpleNamespace

import pytest

from domains.client_finance.obligation_planning import (
    ClientFinanceTermsFacts,
    ClientPaymentTerms,
)
from infrastructure.mysql import beclass_financial_sync as module
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD


class _Cursor:
    def __init__(self):
        self.lastrowid = 0
        self.rowcount = 0
        self.statements = []
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))
        if "FROM client_payment_terms" in statement:
            self.current = {
                "policy_version": "citizen-v1",
                "client_hourly_rate_ntd": 300,
            }
        elif statement.startswith("SELECT case_no FROM client_finance_accounts"):
            self.current = {"case_no": parameters[0]}
        elif statement.startswith("SELECT"):
            self.current = None
        elif "INSERT INTO client_payment_terms_events" in statement:
            self.lastrowid = 31
            self.current = None
        elif "UPDATE client_payment_terms" in statement:
            self.rowcount = 1
            self.current = None

    def fetchone(self):
        return self.current


class _Connection:
    def __init__(self):
        self.cursor_value = _Cursor()

    def cursor(self):
        return self.cursor_value


def test_financial_sync_persists_450_terms_and_client_obligation_impact(monkeypatch):
    connection = _Connection()
    finance_facts = SimpleNamespace(
        case_no="CASE-450",
        account_version=4,
        payment_terms=SimpleNamespace(
            client_hourly_rate=MoneyNTD(450),
            deposit_service_days=5,
            deposit_due_date=date(2026, 9, 1),
            first_payment_due_date=date(2026, 10, 1),
            second_payment_due_date=date(2026, 11, 1),
        ),
    )
    finance_candidate = SimpleNamespace(name="finance-candidate")
    persisted = []
    monkeypatch.setattr(module, "preflight_staff_ids", lambda *_: ())
    monkeypatch.setattr(
        module,
        "load_locked_facts",
        lambda *_: SimpleNamespace(scheduling=SimpleNamespace(segments=())),
    )
    monkeypatch.setattr(module, "select_order", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        module,
        "load_contract_client_finance_facts",
        lambda *_args, **_kwargs: finance_facts,
    )
    monkeypatch.setattr(
        module,
        "build_client_finance_rate_correction_candidate",
        lambda facts, identity: finance_candidate,
    )
    monkeypatch.setattr(
        module,
        "persist_client_finance_terms_impact",
        lambda cursor, command: persisted.append(command),
    )

    module.MySqlBeClassFinancialSync(connection).apply(
        case_no="CASE-450",
        correction_event_id=9,
        actor=ActorContext("admin"),
        reason="correct twins before service",
        idempotency_key=IdempotencyKey("beclass-correction-9"),
        correlation_id=CorrelationId("beclass-correction-test"),
    )

    statements = connection.cursor_value.statements
    event_values = next(
        values
        for statement, values in statements
        if "INSERT INTO client_payment_terms_events" in statement
    )
    assert event_values[2] == 450
    assert any("UPDATE client_payment_terms" in statement for statement, _ in statements)
    assert persisted[0].candidate is finance_candidate
    assert persisted[0].source_event_id == 9


def test_unassigned_40_day_case_corrects_rate_without_creating_obligations(monkeypatch):
    connection = _Connection()
    finance_facts = ClientFinanceTermsFacts(
        case_no="CASE-40-DAYS",
        account_version=4,
        service_hours_per_day=8,
        floor_fee=MoneyNTD(0),
        charge_days=(),
        payment_terms=ClientPaymentTerms(
            deposit_service_days=5,
            client_hourly_rate=MoneyNTD(450),
            deposit_due_date=date(2026, 9, 1),
            first_payment_due_date=date(2026, 10, 1),
            second_payment_due_date=None,
        ),
        existing_obligations=(),
    )
    monkeypatch.setattr(module, "preflight_staff_ids", lambda *_: ())
    monkeypatch.setattr(
        module,
        "load_locked_facts",
        lambda *_: SimpleNamespace(scheduling=SimpleNamespace(segments=())),
    )
    monkeypatch.setattr(
        module, "select_order", lambda *_args, **_kwargs: {"service_days": 40}
    )
    monkeypatch.setattr(
        module,
        "load_contract_client_finance_facts",
        lambda *_args, **_kwargs: finance_facts,
    )

    module.MySqlBeClassFinancialSync(connection).apply(
        case_no="CASE-40-DAYS",
        correction_event_id=9,
        actor=ActorContext("admin"),
        reason="correct twins before matching",
        idempotency_key=IdempotencyKey("beclass-correction-unassigned"),
        correlation_id=CorrelationId("beclass-correction-unassigned"),
    )

    statements = connection.cursor_value.statements
    event_values = next(
        values for statement, values in statements
        if "INSERT INTO client_payment_terms_events" in statement
    )
    assert event_values[2:4] == (450, 5)
    assert next(
        values for statement, values in statements
        if "UPDATE client_finance_accounts" in statement
    ) == (5, "CASE-40-DAYS", 4)
    assert any("INSERT INTO client_finance_outbox" in sql for sql, _ in statements)
    assert not any("INSERT INTO client_obligation" in sql for sql, _ in statements)
    assert not any("staff_obligation" in sql and not sql.startswith("SELECT") for sql, _ in statements)


def _apply(connection):
    module.MySqlBeClassFinancialSync(connection).apply(
        case_no="CASE-INCOMPLETE", correction_event_id=9,
        actor=ActorContext("admin"), reason="correct birth count before service",
        idempotency_key=IdempotencyKey("beclass-incomplete"), correlation_id=CorrelationId("beclass-test"),
    )


def _presence_connection(monkeypatch, present_tables):
    connection = _Connection()
    original = connection.cursor_value.execute
    def execute(statement, parameters):
        original(statement, parameters)
        if statement.startswith("SELECT case_no FROM"):
            table = statement.split()[3]
            connection.cursor_value.current = {"case_no": parameters[0]} if table in present_tables else None
    connection.cursor_value.execute = execute
    monkeypatch.setattr(module, "select_order", lambda *_args, **_kwargs: {"start_date": None})
    return connection


def test_incomplete_unassigned_case_without_financial_roots_only_keeps_effective_correction(monkeypatch):
    connection = _presence_connection(monkeypatch, set())
    def forbidden(*_args, **_kwargs):
        pytest.fail("missing roots must not request full financial facts or bootstrap")
    monkeypatch.setattr(module, "load_locked_facts", forbidden)
    monkeypatch.setattr(module, "load_contract_client_finance_facts", forbidden)
    _apply(connection)
    assert all(sql.startswith("SELECT") for sql, _ in connection.cursor_value.statements)


@pytest.mark.parametrize("tables,code", [
    ({"client_finance_accounts"}, "invalid_client_finance_facts"),
    ({"client_payment_terms"}, "invalid_client_finance_facts"),
    ({"client_obligation_events"}, "invalid_client_finance_facts"),
    ({"client_ledger_entries"}, "invalid_client_finance_facts"),
    ({"payroll_case_accounts"}, "invalid_payroll_facts"),
    ({"case_payroll_rate_policy_snapshots"}, "invalid_payroll_facts"),
    ({"staff_obligation_events"}, "invalid_payroll_facts"),
    ({"payroll_case_accounts", "case_payroll_rate_policy_snapshots", "staff_obligations"},
     "beclass_rate_correction_payroll_facts_inconsistent"),
])
def test_partial_or_orphan_financial_facts_still_block_without_writes(monkeypatch, tables, code):
    connection = _presence_connection(monkeypatch, tables)
    with pytest.raises(ValueError, match=f"^{code}$"):
        _apply(connection)
    assert all(sql.startswith("SELECT") for sql, _ in connection.cursor_value.statements)


def test_existing_assignment_still_updates_both_financial_owners(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(module, "select_order", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(module, "_load_rate_correction_presence", lambda *_: (True, True))
    monkeypatch.setattr(module, "preflight_staff_ids", lambda *_: (7,))
    facts = SimpleNamespace(scheduling="schedule", payroll="payroll", order=SimpleNamespace(terms="terms"), planned_service_dates=())
    monkeypatch.setattr(module, "load_locked_facts", lambda *_: facts)
    monkeypatch.setattr(module, "load_contract_client_finance_facts", lambda *_args, **_kwargs: "finance")
    monkeypatch.setattr(module, "_persist_effective_client_rate", lambda *_: None)
    monkeypatch.setattr(module, "build_client_finance_rate_correction_candidate", lambda *_: "client-impact")
    calls = []
    monkeypatch.setattr(module, "persist_client_finance_terms_impact", lambda *_: calls.append("finance"))
    monkeypatch.setattr(module, "build_generation_candidate", lambda *_: SimpleNamespace(
        assignments=(SimpleNamespace(candidate_key="existing", source_assignment_id=7),)))
    monkeypatch.setattr(module, "build_payroll_rate_correction_impact", lambda *_: SimpleNamespace())
    monkeypatch.setattr(module, "replace", lambda candidate, **_kwargs: candidate)
    monkeypatch.setattr(module, "persist_payroll_terms_impact", lambda *_: calls.append("payroll"))
    _apply(connection)
    assert calls == ["finance", "payroll"]


def test_formal_assignment_cannot_skip_missing_financial_roots(monkeypatch):
    connection = _presence_connection(monkeypatch, set())
    monkeypatch.setattr(module, "_select_assignments", lambda *_: ({"id": 7},))
    with pytest.raises(ValueError, match="^beclass_rate_correction_assignment_facts_inconsistent$"):
        _apply(connection)
    assert all(sql.startswith("SELECT") for sql, _ in connection.cursor_value.statements)
