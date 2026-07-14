from services import db_service


class FakeCursor:
    def __init__(self):
        self.rowcount = 1
        self.sql = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


def test_payment_totals_are_derived_from_three_stages(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(db_service, "get_connection", lambda: connection)

    success = db_service.update_payment_details(
        case_no="115000001",
        deposit_receivable=16000,
        deposit_received=16000,
        first_payment_receivable=42000,
        first_payment_received=40000,
        second_payment_receivable=42000,
        second_payment_received=10000,
        caregiver_fee=80000,
        payment_status="已收二期款",
    )

    assert success is True
    assert connection.committed is True
    assert connection.cursor_instance.params[12] == 100000
    assert connection.cursor_instance.params[13] == 66000
    assert "amount_receivable = %s" in connection.cursor_instance.sql
    assert "amount_received = %s" in connection.cursor_instance.sql
