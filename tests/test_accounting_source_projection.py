from services import accounting_source_projection as projection


class FakeCursor:
    def __init__(self):
        self.calls = []
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if "FROM orders o" in sql:
            self._result = {
                "status": "服務中", "service_days": 20, "service_hours_per_day": 9,
                "floor_fee": 900,
                "start_date": "2026-05-01", "end_date": "2026-05-20",
                "actual_start_date": "2026-05-01", "actual_end_date": "2026-05-20",
                "deposit_service_days": 5, "deposit_due_date": "2026-04-26",
                "client_id": 3, "client_name": "王小明", "identity_status": "一般市民",
                "client_phone": "0912", "client_city": "台中市", "client_address": "中區",
                "service_time": "9小時", "service_type": "週日休", "beclass_query_no": "115000001",
                "refund_bank_code": "812", "refund_account_no": "00123", "survey_details": {"身分證字號": "A123"},
            }
        elif "FROM case_staff_assignments" in sql:
            self._result = [{
                "assignment_id": 9, "case_no": "115000001", "staff_id": 7,
                "assignment_sequence": 1, "planned_hours": 180, "actual_hours": 175,
                "hourly_rate": 350, "floor_fee_allocated": 900, "status": "completed",
                "staff_name": "林月嫂", "staff_identity_card": "B234", "staff_phone": "0922",
                "staff_city": "台中市", "staff_address": "西區",
            }]
        else:
            self._result = [{"staff_id": 7, "bank_code": "807", "branch_code": "001", "account_no": "12345"}]

    def fetchone(self):
        return self._result

    def fetchall(self):
        return self._result


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_projects_raw_source_tables_and_explicit_gaps(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(projection, "get_connection", lambda: connection)

    result = projection.load_case_accounting_source("115000001")

    assert result["case_no"] == "115000001"
    assert result["client"]["client_name"] == "王小明"
    assert result["client"]["identity_status"] == "一般市民"
    assert "clients.identity_status" not in result["order"]
    assert result["beclass"]["refund_account_no"] == "00123"
    assert result["staff_assignments"][0]["actual_hours"] == 175
    assert result["staff_primary_bank_accounts"][0]["account_no"] == "12345"
    assert result["collection_schedule"] == {
        "deposit_service_days": 5,
        "deposit_due_date": "2026-04-26",
    }
    assert result["missing_terms"] == []
    queries = "\n".join(sql for sql, _params in connection.cursor_instance.calls)
    assert "o.deposit_service_days" in queries
    assert "cp.deposit_due_date" in queries
    assert "LEFT JOIN client_payments cp ON cp.case_no = o.case_no" in queries
    assert "v_order_details" not in queries.lower()
    assert "order_id" not in queries.lower()
    assert "o.clients.identity_status" not in queries
    assert "c.identity_status" in queries
    assert connection.closed is True


def test_missing_assignment_rate_is_reported(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(projection, "get_connection", lambda: connection)
    original_execute = connection.cursor_instance.execute

    def execute_without_rate(sql, params):
        original_execute(sql, params)
        if "FROM case_staff_assignments" in sql:
            connection.cursor_instance._result[0]["hourly_rate"] = None

    connection.cursor_instance.execute = execute_without_rate

    result = projection.load_case_accounting_source("115000001")

    assert "assignment:9:hourly_rate" in result["missing_terms"]


def test_missing_collection_terms_are_reported_without_defaults(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(projection, "get_connection", lambda: connection)
    original_execute = connection.cursor_instance.execute

    def execute_without_schedule_terms(sql, params):
        original_execute(sql, params)
        if "FROM orders o" in sql:
            connection.cursor_instance._result["deposit_service_days"] = None
            connection.cursor_instance._result["deposit_due_date"] = None
            connection.cursor_instance._result["actual_start_date"] = None

    connection.cursor_instance.execute = execute_without_schedule_terms

    result = projection.load_case_accounting_source("115000001")

    assert result["collection_schedule"] == {
        "deposit_service_days": None,
        "deposit_due_date": None,
    }
    assert result["missing_terms"] == [
        "orders.deposit_service_days",
        "client_payments.deposit_due_date",
        "orders.actual_start_date",
    ]


def test_cursor_core_reuses_caller_transaction_without_owning_lifecycle(monkeypatch):
    cursor = FakeCursor()
    monkeypatch.setattr(
        projection,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("core opened a connection")),
    )

    result = projection.load_case_accounting_source_with_cursor(cursor, "115000001")

    assert result["case_no"] == "115000001"
    assert len(cursor.calls) == 3
