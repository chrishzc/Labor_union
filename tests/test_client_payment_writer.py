from services import client_payment_writer as writer
from services.client_payment_writer import build_client_summary_update


class FakeCursor:
    def __init__(self):
        self.executed = []
        self._fetchall = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        return {
            "id": 1,
            "case_no": "115000001",
            "deposit_receivable": 1000,
            "first_payment_receivable": 0,
            "second_payment_receivable": 0,
        }

    def fetchall(self):
        return self._fetchall


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        raise AssertionError("writer should not roll back a valid transaction")

    def close(self):
        self.closed = True


def test_summary_updates_only_active_receipt_stages():
    result = build_client_summary_update(
        {"deposit": 1000, "first_payment": 0, "second_payment": 0},
        [
            {"external_reference": "in", "stage": "deposit", "transaction_type": "receipt", "transaction_status": "succeeded", "amount": 1000},
        ],
        "2026-07-14",
    )
    assert result["amount_received"] == 1000.0
    assert result["deposit_received_at"] == "2026-07-14"
    assert result["first_payment_received_at"] is None


def test_first_settlement_sets_second_due_date_from_actual_receipt_date():
    result = build_client_summary_update(
        {"deposit": 1000, "first_payment": 2000, "second_payment": 3000},
        [
            {"external_reference": "deposit", "stage": "deposit", "transaction_type": "receipt", "transaction_status": "succeeded", "amount": 1000, "occurred_at": "2026-05-01"},
            {"external_reference": "first-part", "stage": "first_payment", "transaction_type": "receipt", "transaction_status": "succeeded", "amount": 1000, "occurred_at": "2026-05-03"},
            {"external_reference": "first-rest", "stage": "first_payment", "transaction_type": "receipt", "transaction_status": "succeeded", "amount": 1000, "occurred_at": "2026-05-06"},
        ],
        "2026-05-06",
    )

    assert result["first_payment_received_at"] == "2026-05-06"
    assert result["second_payment_due_date"] == "2026-05-21"


def test_zero_receivable_stage_never_gets_a_settlement_date():
    result = build_client_summary_update(
        {"deposit": 1000, "first_payment": 0, "second_payment": 0},
        [{"external_reference": "deposit", "stage": "deposit", "transaction_type": "receipt", "transaction_status": "succeeded", "amount": 1000}],
        "2026-07-14",
    )

    assert result["first_payment_received_at"] is None
    assert result["second_payment_due_date"] is None


def test_deposit_settlement_updates_summary_and_promotes_talking_case(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(writer, "get_connection", lambda: connection)

    result = writer.record_client_payment_transaction(
        1, "deposit", "receipt", "succeeded", 1000, "2026-07-14", "bank-1",
    )

    statements = [statement for statement, _ in connection.cursor_instance.executed]
    assert result["deposit_received_at"] == "2026-07-14"
    assert connection.committed is True
    assert connection.closed is True
    assert any("second_payment_due_date=%s WHERE id=%s" in statement for statement in statements)
    assert any("SET status = '訂單成立'" in statement for statement in statements)
