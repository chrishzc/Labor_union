from __future__ import annotations

from datetime import date

from domains.client_finance.historical_payment import (
    HistoricalClientConfirmationKind,
    HistoricalClientDirection,
    HistoricalClientObligation,
    HistoricalClientPaymentFacts,
    HistoricalClientPaymentIntent,
    HistoricalClientSourceAvailability,
    build_historical_client_payment_candidate,
)
from infrastructure.mysql.historical_client_payment_repository import MySqlHistoricalClientPaymentRepository
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.historical_payment_settlement import (
    ApplyHistoricalClientPayment,
    HistoricalClientPaymentReceipt,
    StoredHistoricalClientPaymentReceipt,
)


class _Cursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, object]] = []
        self.statement = ""
        self.lastrowid = 91
        self.rowcount = 1

    def execute(self, statement, parameters=None):
        self.statement = statement
        self.statements.append((statement, parameters))

    def executemany(self, statement, rows):
        self.statement = statement
        self.statements.append((statement, tuple(rows)))

    def fetchone(self):
        if "SELECT aggregate_version FROM client_finance_accounts" in self.statement:
            return {"aggregate_version": 7}
        if "SELECT id FROM historical_order_adoption_receipts" in self.statement:
            return {"id": 41}
        return None

    def fetchall(self):
        if "FROM historical_client_payment_projections" in self.statement:
            return [{
                "obligation_identity": "client-obligation:1",
                "amount_snapshot_ntd": 1200,
                "obligation_projection_version": 3,
            }]
        if "FROM client_obligations" in self.statement:
            return [{
                "obligation_identity": "client-obligation:1",
                "case_no": "H-CLIENT-1",
                "obligation_type": "first",
                "direction": "receivable_from_client",
                "amount_due_ntd": 1200,
                "projection_version": 3,
                "status": "open",
            }]
        if "FROM finance_import_rows" in self.statement:
            return [{"id": 17}]
        return []

    def close(self):
        pass


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True


def _intent():
    return HistoricalClientPaymentIntent(
        "H-CLIENT-1",
        HistoricalClientDirection.RECEIVABLE_FROM_CLIENT,
        HistoricalClientConfirmationKind.PAID,
        ("client-obligation:1",),
        date(2025, 1, 8),
        None,
        HistoricalClientSourceAvailability.MISSING,
        "masked-ledger:12",
    )


def _facts(bank=()):
    return HistoricalClientPaymentFacts(
        "H-CLIENT-1",
        7,
        41,
        True,
        bank,
        (HistoricalClientObligation(
            "client-obligation:1",
            "H-CLIENT-1",
            "first",
            HistoricalClientDirection.RECEIVABLE_FROM_CLIENT,
            1200,
            3,
            "open",
        ),),
    )


def test_load_fresh_locks_owner_adoption_obligations_and_bank_candidates() -> None:
    connection = _Connection()
    facts = MySqlHistoricalClientPaymentRepository(connection).load("H-CLIENT-1", for_update=True)

    assert facts.account_version == 7
    assert facts.adoption_receipt_id == 41
    assert facts.normal_bank_candidate_identities == ("17",)
    assert facts.obligations[0].projection_version == 3
    statements = [item[0] for item in connection.cursor_instance.statements]
    assert statements[0].startswith("INSERT IGNORE INTO client_finance_accounts")
    assert all("FOR UPDATE" in statement for statement in statements[1:])
    assert connection.committed is False


def test_load_projections_returns_client_owner_readback_source() -> None:
    connection = _Connection()
    projections = MySqlHistoricalClientPaymentRepository(connection).load_projections(
        "H-CLIENT-1"
    )

    assert projections[0].obligation_identity == "client-obligation:1"
    assert projections[0].obligation_projection_version == 3
    statement, parameters = connection.cursor_instance.statements[-1]
    assert "historical_client_payment_projections" in statement
    assert parameters == ("H-CLIENT-1",)
    assert connection.committed is False


def test_persistence_uses_client_owner_tables_and_existing_receipt_without_commit() -> None:
    connection = _Connection()
    repository = MySqlHistoricalClientPaymentRepository(connection)
    candidate = build_historical_client_payment_candidate(_facts(), _intent())
    request = ApplyHistoricalClientPayment(
        _intent(),
        ExpectedVersion(7),
        41,
        candidate.fingerprint,
        IdempotencyKey("historical-client:1"),
        ActorContext("finance:8"),
        "Confirm adopted pre-system payment.",
        CorrelationId("historical-client-correlation"),
    )
    event_identity = "historical-client-payment:" + "a" * 64
    event_id = repository.append_event(request, candidate, event_identity)
    repository.append_obligation_links(event_id, candidate)
    repository.upsert_projections(event_id, candidate, 8)
    repository.append_source_outbox(event_id, candidate, event_identity)
    receipt = HistoricalClientPaymentReceipt(
        event_identity,
        "H-CLIENT-1",
        ("client-obligation:1",),
        1200,
        8,
        candidate.fingerprint,
    )
    repository.save_receipt(
        request.idempotency_key,
        StoredHistoricalClientPaymentReceipt(fingerprint_payload({"command": 1}), receipt),
    )

    statements = "\n".join(item[0] for item in connection.cursor_instance.statements)
    assert "INSERT INTO historical_client_payment_events" in statements
    assert "INSERT INTO historical_client_payment_obligation_links" in statements
    assert "INSERT INTO historical_client_payment_projections" in statements
    assert "UPDATE client_finance_accounts" in statements
    assert "INSERT INTO historical_client_payment_source_outbox" in statements
    assert "INSERT INTO client_finance_apply_receipts" in statements
    assert "staff_" not in statements
    assert "finance_import_row_id" not in statements
    assert connection.committed is False
