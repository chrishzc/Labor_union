"""Execute the receipt summary SQL through its adapter and authenticated GET contract."""

from contextlib import closing
from dataclasses import asdict
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.client_payments import get_client_finance_query_application
from api.routes.client_payments import get_all_client_payments, router
from api.schemas.client_payments import ClientFinanceCaseSummaryView
from infrastructure.mysql.client_payments_query_repository import MySqlClientFinanceQueryRepository
from subsystems.client_finance.client_payments_query import ClientFinanceQueryApplication


@pytest.fixture
def summary_repository():
    with closing(sqlite3.connect(":memory:", check_same_thread=False)) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE client_finance_accounts (case_no TEXT, aggregate_version INTEGER);
            CREATE TABLE client_obligations (case_no TEXT, obligation_identity TEXT,
                direction TEXT, status TEXT, amount_due_ntd INTEGER, projection_version INTEGER DEFAULT 1);
            CREATE TABLE client_ledger_entries (case_no TEXT, entry_type TEXT,
                id INTEGER PRIMARY KEY, amount_ntd INTEGER DEFAULT 2500, reversal_of_entry_id INTEGER);
            CREATE TABLE historical_client_payment_projections (obligation_identity TEXT,
                confirmation_kind TEXT, amount_snapshot_ntd INTEGER, obligation_projection_version INTEGER);
        """)
        for entry_type in ("receipt", "refund", "adjustment", "reversal", "subsidy_return", "subsidy_advance"):
            connection.execute("INSERT INTO client_finance_accounts VALUES (?, 3)", (entry_type,))
            connection.execute("INSERT INTO client_ledger_entries (case_no,entry_type) VALUES (?, ?)", (entry_type, entry_type))
        connection.execute("INSERT INTO client_finance_accounts VALUES ('empty', 0)")
        connection.execute("INSERT INTO client_ledger_entries (case_no,entry_type) VALUES ('receipt', 'refund')")
        connection.executemany("INSERT INTO client_obligations (case_no,obligation_identity,direction,status,amount_due_ntd) VALUES ('receipt', ?, 'receivable_from_client', 'open', 2500)", [("first",), ("second",)])
        for case_no in ("paid", "historical-paid", "historical-settled", "historical-stale", "reversed"):
            connection.execute("INSERT INTO client_finance_accounts VALUES (?, 3)", (case_no,))
            connection.execute("INSERT INTO client_obligations VALUES (?, ?, 'receivable_from_client', ?, ?, 1)",
                               (case_no, case_no, "settled" if case_no == "paid" else "open", 0 if case_no == "paid" else 2500))
        connection.execute("INSERT INTO client_ledger_entries (id,case_no,entry_type) VALUES (100,'paid','receipt')")
        connection.execute("INSERT INTO client_ledger_entries (id,case_no,entry_type) VALUES (101,'reversed','receipt')")
        connection.execute("INSERT INTO client_ledger_entries (case_no,entry_type,reversal_of_entry_id) VALUES ('reversed','reversal',101)")
        connection.executemany("INSERT INTO historical_client_payment_projections VALUES (?, ?, 2500, ?)",
                               [("historical-paid", "paid", 1), ("historical-settled", "settled", 1), ("historical-stale", "paid", 0)])
        repository = MySqlClientFinanceQueryRepository(SimpleNamespace(cursor=lambda: closing(connection.cursor())))
        yield repository


def test_receipt_summary_counts_only_actual_receipts_without_join_multiplication(summary_repository):
    application = ClientFinanceQueryApplication(summary_repository)
    result = application.query_all()
    rows = {row.case_no: ClientFinanceCaseSummaryView.model_validate(asdict(row)).model_dump() for row in result.cases}
    _assert_summary(rows)
    response = get_all_client_payments(principal=SimpleNamespace(), application=application)
    _assert_summary({row["case_no"]: row for row in response.model_dump()["data"]["cases"]})


def test_receipt_summary_authenticated_get_contract(summary_repository, monkeypatch):
    monkeypatch.setenv('ENABLE_ADMIN_AUTH', 'true')
    application = ClientFinanceQueryApplication(summary_repository)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_client_finance_query_application] = lambda: application
    with TestClient(app) as client:
        assert client.get("/api/v1/client-payments").status_code == 401
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace()
        response = client.get("/api/v1/client-payments")
    assert response.status_code == 200
    _assert_summary({row["case_no"]: row for row in response.json()["data"]["cases"]})


def _assert_summary(rows):
    assert rows["receipt"]["receipt_entry_count"] == 1
    assert rows["receipt"]["ledger_entry_count"] == 2
    assert rows["receipt"]["open_receivable_amount_ntd"] == 5000
    assert rows["receipt"]["receipt_status"] == "partially_received"
    assert rows["paid"]["receipt_status"] == "received"
    assert rows["historical-paid"]["receipt_status"] == "received"
    assert rows["historical-paid"]["receipt_entry_count"] == 0
    assert rows["historical-paid"]["open_receivable_amount_ntd"] == 0
    assert rows["historical-settled"]["receipt_status"] == "settled"
    assert rows["historical-stale"]["receipt_status"] == "unpaid"
    assert rows["historical-stale"]["open_receivable_amount_ntd"] == 2500
    assert rows["reversed"]["receipt_status"] == "unpaid"
    assert rows["empty"]["receipt_status"] == "pending"
    for case_no in ("refund", "adjustment", "reversal", "subsidy_return", "subsidy_advance", "empty"):
        assert rows[case_no]["receipt_entry_count"] == 0
