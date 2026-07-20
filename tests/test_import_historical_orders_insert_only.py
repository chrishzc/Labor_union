from __future__ import annotations

import importlib

import pandas as pd


historical = importlib.import_module("scripts.import_historical_orders")


class Cursor:
    def __init__(self, existing_orders=(), client_ids=None, fail_on=None):
        self.existing_orders = set(existing_orders)
        self.client_ids = client_ids or {}
        self.fail_on = fail_on
        self.calls = []
        self.query_kind = None
        self.current_case_no = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.calls.append((compact, params))
        if self.fail_on and self.fail_on in compact:
            raise RuntimeError("injected insert failure")
        self.current_case_no = params[0] if params else None
        if compact.startswith("SELECT COUNT(*) AS record_count FROM orders"):
            self.query_kind = "order"
        elif compact.startswith("SELECT id FROM clients WHERE case_no"):
            self.query_kind = "client"

    def fetchone(self):
        if self.query_kind == "order":
            return {"record_count": int(self.current_case_no in self.existing_orders)}
        raise AssertionError("unexpected fetchone")

    def fetchall(self):
        if self.query_kind == "client":
            return [{"id": client_id} for client_id in self.client_ids.get(self.current_case_no, [])]
        raise AssertionError("unexpected fetchall")


class Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        pass

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _patch_import(monkeypatch, frame, connection):
    monkeypatch.setattr(historical.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(historical, "load_historical_frame", lambda _path: frame)
    monkeypatch.setattr(historical.pymysql, "connect", lambda **_kwargs: connection)


def test_only_inserts_case_with_unique_client_relation(monkeypatch):
    frame = pd.DataFrame([
        {"case_no": "new-001", "client_name": "名稱不得作為關聯", "staff_name": "人員名稱不得作為關聯", "status": 2},
        {"case_no": "old-001", "status": 0},
        {"case_no": "missing-client", "status": 1},
        {"case_no": "duplicate-client", "status": 1},
        {"case_no": None, "client_name": "不可用姓名猜測"},
    ])
    cursor = Cursor(
        existing_orders={"old-001"},
        client_ids={"new-001": [11], "missing-client": [], "duplicate-client": [21, 22]},
    )
    connection = Connection(cursor)
    _patch_import(monkeypatch, frame, connection)

    result = historical.process_import("historical.xlsx")
    statements = [sql for sql, _ in cursor.calls]

    assert result == {"inserted": 1, "skipped_existing": 1, "review_required": 3, "failed": 0}
    assert not any(sql.startswith("UPDATE") for sql in statements)
    assert not any("WHERE name" in sql for sql in statements)
    insert_calls = [(sql, params) for sql, params in cursor.calls if sql.startswith("INSERT INTO orders")]
    assert len(insert_calls) == 1
    assert insert_calls[0][1] == ("new-001", 11, None, None, "洽談中")
    assert connection.rollbacks == 0
    assert connection.closed is True


def test_order_insert_failure_rolls_back(monkeypatch):
    frame = pd.DataFrame([{"case_no": "new-001", "status": 1}])
    cursor = Cursor(client_ids={"new-001": [11]}, fail_on="INSERT INTO orders")
    connection = Connection(cursor)
    _patch_import(monkeypatch, frame, connection)

    result = historical.process_import("historical.xlsx")

    assert result["inserted"] == 0
    assert result["failed"] == 1
    assert connection.rollbacks == 1
    assert connection.closed is True
