from __future__ import annotations

from datetime import date

from domains.staff_payables.historical_payout import (
    HistoricalStaffConfirmationKind,
    HistoricalStaffObligation,
    HistoricalStaffPayoutFacts,
    HistoricalStaffPayoutIntent,
    HistoricalStaffSourceAvailability,
    build_historical_staff_payout_candidate,
)
from infrastructure.mysql.historical_staff_payout_repository import MySqlHistoricalStaffPayoutRepository
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.staff_payables.historical_payment_settlement import (
    ApplyHistoricalStaffPayout,
    HistoricalStaffPayoutReceipt,
    StoredHistoricalStaffPayoutReceipt,
)


class _Cursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, object]] = []
        self.statement = ""
        self.lastrowid = 92
        self.rowcount = 1

    def execute(self, statement, parameters=None):
        self.statement = statement
        self.statements.append((statement, parameters))

    def executemany(self, statement, rows):
        self.statement = statement
        self.statements.append((statement, tuple(rows)))

    def fetchone(self):
        if "SELECT aggregate_version FROM staff_payable_accounts" in self.statement:
            return {"aggregate_version": 6}
        if "SELECT id FROM historical_order_adoption_receipts" in self.statement:
            return {"id": 42}
        return None

    def fetchall(self):
        if "FROM historical_staff_payout_projections" in self.statement:
            return [{
                "obligation_identity": "staff-obligation:1",
                "amount_snapshot_ntd": 1800,
                "obligation_payroll_version": 4,
            }]
        if "FROM staff_obligations" in self.statement:
            return [{
                "obligation_identity": "staff-obligation:1",
                "case_no": "H-STAFF-1",
                "staff_id": 9,
                "amount_due_ntd": 1800,
                "payroll_version": 4,
                "direction": "payable_to_staff",
                "status": "open",
            }]
        if "FROM finance_import_rows" in self.statement:
            return [{"id": 18}]
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
    return HistoricalStaffPayoutIntent(
        "H-STAFF-1",
        9,
        HistoricalStaffConfirmationKind.PAID,
        ("staff-obligation:1",),
        date(2025, 2, 3),
        None,
        HistoricalStaffSourceAvailability.UNRECOVERABLE,
        "masked-payout:8",
    )


def _facts(bank=()):
    return HistoricalStaffPayoutFacts(
        "H-STAFF-1",
        9,
        6,
        42,
        True,
        bank,
        (HistoricalStaffObligation(
            "staff-obligation:1",
            "H-STAFF-1",
            9,
            1800,
            4,
            "payable_to_staff",
            "open",
        ),),
    )


def test_load_fresh_locks_staff_owner_adoption_obligations_and_bank_candidates() -> None:
    connection = _Connection()
    facts = MySqlHistoricalStaffPayoutRepository(connection).load("H-STAFF-1", 9, for_update=True)

    assert facts.staff_payables_version == 6
    assert facts.adoption_receipt_id == 42
    assert facts.normal_bank_candidate_identities == ("18",)
    assert facts.obligations[0].payroll_version == 4
    statements = [item[0] for item in connection.cursor_instance.statements]
    assert statements[0].startswith("INSERT IGNORE INTO staff_payable_accounts")
    assert all("FOR UPDATE" in statement for statement in statements[1:])
    assert connection.committed is False


def test_load_projections_returns_staff_owner_readback_source() -> None:
    connection = _Connection()
    projections = MySqlHistoricalStaffPayoutRepository(connection).load_projections(
        "H-STAFF-1", 9
    )

    assert projections[0].obligation_identity == "staff-obligation:1"
    assert projections[0].obligation_payroll_version == 4
    statement, parameters = connection.cursor_instance.statements[-1]
    assert "historical_staff_payout_projections" in statement
    assert parameters == ("H-STAFF-1", 9)
    assert connection.committed is False


def test_persistence_uses_staff_owner_tables_and_existing_receipt_without_commit() -> None:
    connection = _Connection()
    repository = MySqlHistoricalStaffPayoutRepository(connection)
    candidate = build_historical_staff_payout_candidate(_facts(), _intent())
    request = ApplyHistoricalStaffPayout(
        _intent(),
        ExpectedVersion(6),
        42,
        candidate.fingerprint,
        IdempotencyKey("historical-staff:1"),
        ActorContext("payables:8"),
        "Confirm adopted pre-system payout.",
        CorrelationId("historical-staff-correlation"),
    )
    event_identity = "historical-staff-payout:" + "b" * 64
    event_id = repository.append_event(request, candidate, event_identity)
    repository.append_obligation_links(event_id, candidate)
    repository.upsert_projections(event_id, candidate, 7)
    repository.append_source_outbox(event_id, candidate, event_identity)
    receipt = HistoricalStaffPayoutReceipt(
        event_identity,
        "H-STAFF-1",
        9,
        ("staff-obligation:1",),
        1800,
        7,
        candidate.fingerprint,
    )
    repository.save_receipt(
        request.idempotency_key,
        StoredHistoricalStaffPayoutReceipt(fingerprint_payload({"command": 1}), receipt),
    )

    statements = "\n".join(item[0] for item in connection.cursor_instance.statements)
    assert "INSERT INTO historical_staff_payout_events" in statements
    assert "INSERT INTO historical_staff_payout_obligation_links" in statements
    assert "INSERT INTO historical_staff_payout_projections" in statements
    assert "UPDATE staff_payable_accounts" in statements
    assert "INSERT INTO historical_staff_payout_source_outbox" in statements
    assert "INSERT INTO staff_payables_apply_receipts" in statements
    assert "historical_client_" not in statements
    assert "finance_import_row_id" not in statements
    assert connection.committed is False
