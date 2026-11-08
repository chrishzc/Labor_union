"""BeClass rate correction coordinates Client Finance in the same transaction."""

from datetime import date
from dataclasses import replace
from types import SimpleNamespace

import pytest

from domains.client_finance.obligation_planning import (
    ClientFinanceTermsFacts,
    ClientPaymentTerms,
    ClientSubsidyReturnPlan,
)
from infrastructure.mysql import beclass_financial_sync as module
from infrastructure.mysql import client_finance_terms_writer as terms_writer
from subsystems.orders.terms_workflow import (
    ClientFinanceImpactPersistenceCommand, PersistedBeClassPaymentTermsChange,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD


class _Cursor:
    def __init__(self):
        self.lastrowid = 0
        self.rowcount = 0
        self.statements = []
        self.current = None
        self.rate = 300
        self.current_event_id = None
        self.account_version = 4
        self.terms_events = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))
        if statement.startswith("SELECT event.id AS terms_event_id"):
            event = self.terms_events.get(self.current_event_id)
            self.current = None if event is None else {
                **event, "current_event_id": self.current_event_id,
                "current_hourly_rate_ntd": self.rate, "aggregate_version": self.account_version,
            }
        elif "FROM client_payment_terms" in statement:
            self.current = {
                "policy_version": "citizen-v1",
                "client_hourly_rate_ntd": self.rate,
            }
        elif statement.startswith("SELECT case_no FROM client_finance_accounts"):
            self.current = {"case_no": parameters[0]}
        elif statement.startswith("SELECT"):
            self.current = None
        elif "INSERT INTO client_payment_terms_events" in statement:
            self.lastrowid = 31
            self.terms_events[31] = {
                "terms_event_id": 31, "case_no": parameters[0],
                "client_hourly_rate_ntd": parameters[2],
                "expected_account_version": parameters[7],
                "source_event_identity": parameters[8], "actor": parameters[10],
            }
            self.current = None
        elif "UPDATE client_payment_terms" in statement:
            self.rate, self.current_event_id = parameters[:2]
            self.rowcount = 1
            self.current = None
        elif "UPDATE client_finance_accounts" in statement:
            self.rowcount = int(parameters[2] == self.account_version)
            if self.rowcount:
                self.account_version = parameters[0]

    def fetchone(self):
        return self.current

    def fetchall(self):
        return [] if self.current is None else [self.current]


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
    monkeypatch.setattr(module, "select_order", lambda *_args, **_kwargs: {
        "start_date": date(2026, 10, 1), "service_days": 5,
        "service_hours_per_day": 8, "floor_fee": 0,
    })
    monkeypatch.setattr(
        module,
        "load_calculable_client_finance_facts",
        lambda *_args, **_kwargs: (finance_facts, None),
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


def test_incomplete_unassigned_case_corrects_existing_terms_without_inventing_days(monkeypatch):
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


def _unassigned_facts():
    return ClientFinanceTermsFacts(
        case_no="CASE-PREWRITTEN", account_version=4, service_hours_per_day=8,
        floor_fee=MoneyNTD(0), charge_days=(),
        payment_terms=ClientPaymentTerms(5, MoneyNTD(450), date(2026, 9, 1), date(2026, 10, 1), None),
        existing_obligations=(),
    )


def _prewritten_command(connection):
    facts = _unassigned_facts()
    change = module._persist_effective_client_rate(
        connection.cursor_value, facts, 9, ActorContext("admin"), "actual rate change",
        IdempotencyKey("prewritten-terms"),
    )
    candidate = module.build_client_finance_rate_correction_candidate(facts, "beclass-rate-correction:9")
    return ClientFinanceImpactPersistenceCommand(
        candidate, IdempotencyKey("prewritten-finance"), ActorContext("admin"), "actual rate change",
        CorrelationId("prewritten-finance"), "beclass-correction", 9, change,
    )


def test_actual_terms_event_is_checked_before_version_and_outbox_once():
    connection = _Connection()
    command = _prewritten_command(connection)
    assert command.persisted_payment_terms_change == PersistedBeClassPaymentTermsChange("CASE-PREWRITTEN", 31, 4, 9)
    terms_writer.persist_client_finance_terms_impact(connection.cursor_value, command)
    statements = connection.cursor_value.statements
    assert connection.cursor_value.account_version == 5
    assert sum("INSERT INTO client_payment_terms_events" in sql for sql, _ in statements) == 1
    assert sum("UPDATE client_finance_accounts" in sql for sql, _ in statements) == 1
    assert sum("INSERT INTO client_finance_outbox" in sql for sql, _ in statements) == 1
    assert not any("INSERT INTO client_obligation" in sql for sql, _ in statements)


def test_already_equal_rate_does_not_emit_terms_version_or_outbox():
    connection = _Connection()
    connection.cursor_value.rate = 450
    command = _prewritten_command(connection)
    assert command.persisted_payment_terms_change is None
    terms_writer.persist_client_finance_terms_impact(connection.cursor_value, command)
    terms_writer.persist_client_finance_terms_impact(connection.cursor_value, command)
    assert connection.cursor_value.account_version == 4
    assert all(sql.startswith("SELECT") for sql, _ in connection.cursor_value.statements)


@pytest.mark.parametrize("mutation", [
    "case", "version", "source", "event", "current_event", "event_case",
    "event_version", "event_source", "event_actor", "rate", "account_version", "untyped", "family",
])
def test_prewritten_terms_mismatch_is_rejected_before_other_writer_changes(monkeypatch, mutation):
    connection = _Connection()
    command = _prewritten_command(connection)
    change = command.persisted_payment_terms_change
    cursor = connection.cursor_value
    if mutation in {"case", "version", "source", "event"}:
        change = replace(change, **{
            "case": {"case_no": "OTHER"}, "version": {"expected_account_version": 3},
            "source": {"correction_event_id": 8}, "event": {"terms_event_id": 32},
        }[mutation])
        command = replace(command, persisted_payment_terms_change=change)
    elif mutation == "family":
        command = replace(command, source_event_family="order-terms")
    elif mutation == "untyped":
        command = replace(command, persisted_payment_terms_change=True)
    elif mutation == "current_event":
        cursor.current_event_id = 999
    elif mutation == "rate":
        cursor.rate = 300
    elif mutation == "account_version":
        cursor.account_version = 5
    else:
        field, value = {
            "event_case": ("case_no", "OTHER"), "event_version": ("expected_account_version", 3),
            "event_source": ("source_event_identity", "beclass-correction:8"),
            "event_actor": ("actor", "other-admin"),
        }[mutation]
        cursor.terms_events[31][field] = value
    before = len(cursor.statements)
    monkeypatch.setattr(terms_writer, "_persist_payment_terms", lambda *_: pytest.fail("proof must be checked first"))
    with pytest.raises(ValueError, match="(invalid_persisted|persisted)_payment_terms_change"):
        terms_writer.persist_client_finance_terms_impact(cursor, command)
    assert all(sql.startswith("SELECT") for sql, _ in cursor.statements[before:])


@pytest.mark.parametrize("field,value", [("terms_event_id", 0), ("correction_event_id", True), ("expected_account_version", -1)])
def test_persisted_terms_change_requires_an_actual_event_identity(field, value):
    values = dict(case_no="CASE", terms_event_id=31, expected_account_version=4, correction_event_id=9)
    values[field] = value
    with pytest.raises(ValueError, match="invalid_persisted_payment_terms_change"):
        PersistedBeClassPaymentTermsChange(**values)


def test_original_account_cas_rowcount_zero_still_rejects_before_outbox():
    connection = _Connection()
    command = _prewritten_command(connection)
    cursor = connection.cursor_value
    execute = cursor.execute

    def reject_cas(statement, parameters):
        if statement.startswith("UPDATE client_finance_accounts"):
            cursor.statements.append((" ".join(statement.split()), parameters))
            cursor.rowcount = 0
        else:
            execute(statement, parameters)

    cursor.execute = reject_cas
    with pytest.raises(RuntimeError, match="^client_finance_candidate_stale$"):
        terms_writer.persist_client_finance_terms_impact(cursor, command)
    assert cursor.account_version == 4
    assert not any("INSERT INTO client_finance_outbox" in sql for sql, _ in cursor.statements)


def test_existing_terminal_subsidy_plan_replay_keeps_the_original_noop_guard():
    class TerminalCursor(_Cursor):
        def execute(self, statement, parameters):
            self.statements.append((" ".join(statement.split()), parameters))
            if "LEFT JOIN client_finance_amount_controls" in statement:
                self.current = None
            elif "FROM client_obligations o JOIN client_obligation_events" in statement:
                self.current = {
                    "obligation_identity": "subsidy:CASE-PREWRITTEN", "amount_due_ntd": 12000,
                    "due_date": date(2026, 11, 15), "after_amount_ntd": 12000,
                }
            elif "FROM client_refund_recipient_snapshots" in statement:
                self.current = {"refund_obligation_identity": "subsidy:CASE-PREWRITTEN"}
            elif " paid " in statement:
                self.current = {"paid": 0}
            elif " recovered " in statement:
                self.current = {"recovered": 0}
            else:
                pytest.fail("Unexpected terminal replay query or mutation")

    facts = _unassigned_facts()
    candidate = replace(module.build_client_finance_rate_correction_candidate(facts, "terminal-current"),
        subsidy_return_plan=ClientSubsidyReturnPlan("subsidy:CASE-PREWRITTEN", MoneyNTD(12000), date(2026, 11, 15)))
    command = ClientFinanceImpactPersistenceCommand(candidate, IdempotencyKey("terminal-current"),
        ActorContext("admin"), "already current", CorrelationId("terminal-current"), "service-completion", 1)
    cursor = TerminalCursor()
    terms_writer.persist_client_finance_terms_impact(cursor, command)
    terms_writer.persist_client_finance_terms_impact(cursor, command)
    assert cursor.account_version == 4
    assert all(sql.startswith("SELECT") for sql, _ in cursor.statements)
