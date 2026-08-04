from datetime import datetime

from subsystems.orders.lifecycle_authoritative_facts_loader import (
    _load_deposit_ledger,
)
from subsystems.orders.lifecycle_control_read_facts import (
    _load_deposit_settlement,
)


class ProjectionCursor:
    def __init__(self, row):
        self._row = row
        self.executed_sql = []

    def execute(self, sql, values):
        self.executed_sql.append((sql, values))

    def fetchone(self):
        return self._row


def test_locked_lifecycle_facts_fail_closed_when_canonical_projection_is_missing():
    cursor = ProjectionCursor(None)

    result = _load_deposit_ledger(cursor, "G14-CASE")

    assert result == (
        False,
        None,
        None,
        ["enter_service.deposit_settlement_missing"],
    )
    assert "client_deposit_settlement_projection" in cursor.executed_sql[0][0]
    assert "client_payments" not in cursor.executed_sql[0][0]


def test_control_read_uses_settled_canonical_projection_identity():
    identity = "a" * 64
    cursor = ProjectionCursor(
        {
            "settlement_state": "settled",
            "settlement_identity": identity,
            "updated_at": datetime(2026, 8, 4, 10, 30),
        }
    )

    result = _load_deposit_settlement(cursor, "G14-CASE")

    assert result == (True, identity, "2026-08-04", ())
    assert "client_deposit_settlement_projection" in cursor.executed_sql[0][0]
    assert "client_payment_transactions" not in cursor.executed_sql[0][0]
