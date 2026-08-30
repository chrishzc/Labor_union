from subsystems.orders.client_finance_outbox_consumer import (
    _activate_reconfirmation_if_current,
    _project_deposit_established,
)


def test_deposit_consumer_projects_established_status_before_contract_completion():
    connection = _Connection(rowcounts=(1, 1))
    event = {
        "case_no": "CASE-1",
        "intent_key": "orders-deposit:CASE-1",
    }
    payload = {"settlement_identity": "a" * 64}

    _project_deposit_established(connection, event, payload)

    assert "status='訂單成立'" in connection.cursor_instance.executed[0][0]
    assert connection.cursor_instance.executed[0][1] == ("CASE-1",)
    assert "'deposit_reconciled'" in connection.cursor_instance.executed[1][0]
    assert connection.cursor_instance.executed[1][1] == (
        "orders-deposit:CASE-1", "a" * 64, "CASE-1",
    )


def test_existing_non_discussion_order_does_not_append_a_second_lifecycle_event():
    connection = _Connection(rowcounts=(0,))

    _project_deposit_established(
        connection,
        {"case_no": "CASE-1", "intent_key": "orders-deposit:CASE-1"},
        {"settlement_identity": "a" * 64},
    )

    assert len(connection.cursor_instance.executed) == 1


def test_deposit_consumer_skips_actual_start_control_when_service_has_not_started():
    connection = _Connection(
        rowcounts=(1,),
        rows=({"lifecycle_version": 1, "actual_start_date": None},),
    )

    _activate_reconfirmation_if_current(
        connection,
        {"case_no": "CASE-1", "intent_key": "orders-deposit:CASE-1"},
        {"settlement_identity": "a" * 64},
    )

    assert len(connection.cursor_instance.executed) == 1


class _Connection:
    def __init__(self, rowcounts, rows=()):
        self.cursor_instance = _Cursor(rowcounts, rows)

    def cursor(self):
        return self.cursor_instance


class _Cursor:
    def __init__(self, rowcounts, rows):
        self._rowcounts = iter(rowcounts)
        self._rows = iter(rows)
        self.executed = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.executed.append((statement, parameters))
        self.rowcount = next(self._rowcounts)

    def fetchone(self):
        return next(self._rows)
