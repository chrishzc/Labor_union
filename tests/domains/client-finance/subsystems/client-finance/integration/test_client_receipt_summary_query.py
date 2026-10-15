"""Execute the receipt summary SQL through its adapter and authenticated GET contract."""

from contextlib import closing
import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.client_payments import get_client_finance_query_application
from api.routes.client_payments import router
from infrastructure.mysql.client_payments_query_repository import MySqlClientFinanceQueryRepository
from subsystems.client_finance.client_payments_query import ClientFinanceQueryApplication


def test_receipt_summary_counts_only_actual_receipts_without_join_multiplication():
    with closing(sqlite3.connect(":memory:", check_same_thread=False)) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE client_finance_accounts (case_no TEXT, aggregate_version INTEGER);
            CREATE TABLE client_obligations (case_no TEXT, obligation_identity TEXT,
                direction TEXT, status TEXT, amount_due_ntd INTEGER);
            CREATE TABLE client_ledger_entries (case_no TEXT, entry_type TEXT);
        """)
        for entry_type in ("receipt", "refund", "adjustment", "reversal", "subsidy_return", "subsidy_advance"):
            connection.execute("INSERT INTO client_finance_accounts VALUES (?, 3)", (entry_type,))
            connection.execute("INSERT INTO client_ledger_entries VALUES (?, ?)", (entry_type, entry_type))
        connection.execute("INSERT INTO client_finance_accounts VALUES ('empty', 0)")
        connection.execute("INSERT INTO client_ledger_entries VALUES ('receipt', 'refund')")
        connection.executemany("INSERT INTO client_obligations VALUES ('receipt', ?, 'receivable_from_client', 'open', 2500)", [("first",), ("second",)])
        repository = MySqlClientFinanceQueryRepository(SimpleNamespace(cursor=lambda: closing(connection.cursor())))
        application = ClientFinanceQueryApplication(repository)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_client_finance_query_application] = lambda: application
        with TestClient(app) as client:
            assert client.get("/api/v1/client-payments").status_code == 401
            app.dependency_overrides[require_admin] = lambda: SimpleNamespace()
            response = client.get("/api/v1/client-payments")
        assert response.status_code == 200
        rows = {row["case_no"]: row for row in response.json()["data"]["cases"]}
        assert rows["receipt"]["receipt_entry_count"] == 1
        assert rows["receipt"]["ledger_entry_count"] == 2
        assert rows["receipt"]["open_receivable_amount_ntd"] == 5000
        for case_no in ("refund", "adjustment", "reversal", "subsidy_return", "subsidy_advance", "empty"):
            assert rows[case_no]["receipt_entry_count"] == 0
