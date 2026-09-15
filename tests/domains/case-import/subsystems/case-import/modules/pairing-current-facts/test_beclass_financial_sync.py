"""BeClass rate correction coordinates Client Finance in the same transaction."""

from datetime import date
from types import SimpleNamespace

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
        "build_client_finance_terms_candidate",
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
