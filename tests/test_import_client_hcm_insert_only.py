from __future__ import annotations

import importlib

import pandas as pd


hcm = importlib.import_module("scripts.imports.import_client_hcm")


class Cursor:
    def __init__(self, existing_case_nos=(), fail_on=None):
        self.existing_case_nos = set(existing_case_nos)
        self.fail_on = fail_on
        self.calls = []
        self.lastrowid = 100
        self.current_case_no = None

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.calls.append((compact, params))
        if self.fail_on and self.fail_on in compact:
            raise RuntimeError("injected insert failure")
        if compact.startswith("SELECT id FROM clients"):
            self.current_case_no = params[0]
        if compact.startswith("INSERT INTO clients"):
            self.lastrowid += 1

    def fetchone(self):
        return (99,) if self.current_case_no in self.existing_case_nos else None


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


class Workbook:
    sheet_names = ["HCM 客戶"]

    def __init__(self, frame):
        self.frame = frame

    def parse(self, sheet_name):
        assert sheet_name == "HCM 客戶"
        return self.frame


def _patch_import(monkeypatch, frame, connection):
    monkeypatch.setattr(hcm.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(hcm.pd, "ExcelFile", lambda _path: Workbook(frame))
    monkeypatch.setattr(hcm.pymysql, "connect", lambda **_kwargs: connection)


def test_mixed_rows_only_insert_new_case_no(monkeypatch):
    frame = pd.DataFrame([
        {"查詢序號(案件編號)": "new-001", "姓名": "新客戶"},
        {"查詢序號(案件編號)": "old-001", "姓名": "既有客戶"},
        {"查詢序號(案件編號)": None, "姓名": "缺案件號"},
    ])
    cursor = Cursor(existing_case_nos={"old-001"})
    connection = Connection(cursor)
    _patch_import(monkeypatch, frame, connection)

    result = hcm.process_import("hcm.xlsx")
    statements = [sql for sql, _ in cursor.calls]

    assert result == {"inserted": 1, "skipped_existing": 1, "review_required": 1, "failed": 0}
    assert not any(sql.startswith("UPDATE") for sql in statements)
    assert sum(sql.startswith("INSERT INTO clients") for sql in statements) == 1
    assert sum(sql.startswith("INSERT INTO orders") for sql in statements) == 1
    assert connection.rollbacks == 0
    assert connection.closed is True


def test_new_order_failure_rolls_back(monkeypatch):
    frame = pd.DataFrame([{"查詢序號(案件編號)": "new-001", "姓名": "新客戶"}])
    cursor = Cursor(fail_on="INSERT INTO orders")
    connection = Connection(cursor)
    _patch_import(monkeypatch, frame, connection)

    result = hcm.process_import("hcm.xlsx")

    assert result["inserted"] == 0
    assert result["failed"] == 1
    assert connection.rollbacks == 1
    assert connection.closed is True
