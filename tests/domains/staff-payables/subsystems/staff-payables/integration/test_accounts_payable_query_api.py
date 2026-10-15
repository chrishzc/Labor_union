"""Partial staff payouts expose the same remaining amount in query, audit and XLSX."""

from datetime import date, datetime, timezone
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from api.dependencies.accounts_payable_export import (
    AccountsPayableExportApplication,
    _ReadOnlySnapshotComposition,
    get_accounts_payable_export_application,
)
from api.dependencies.admin_auth import require_admin
from api.routes.finance_reports import router
from infrastructure.mysql.accounts_payable_export_sources import (
    MySqlClientRefundExportSource,
    MySqlStaffPayableExportSource,
    _CLIENT_REFUNDS_SQL,
    _HISTORICAL_STAFF_PAYABLE_PROJECTION_SQL,
    _STAFF_PAYABLE_CASE_AUDIT_SQL,
    _STAFF_PAYABLES_SQL,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff_payables.accounts_payable_export import (
    AccountsPayableExportWorkflow,
    ArchivedWorkbook,
)

URL = "/api/v1/finance-reports/accounts-payable"


class _Connection:
    def __init__(self):
        self.row = {
            "obligation_identity": "service:CASE-P:assignment:7",
            "case_no": "CASE-P", "staff_id": 7, "recipient_name": "月嫂甲",
            "identity_card": "", "amount_due_ntd": 20_000,
            "export_amount_ntd": 1500, "due_date": date(2026, 3, 15),
            "order_due_date": date(2026, 3, 15), "payout_status": "partially_paid",
            "primary_account_count": 1, "bank_code": "012", "account_no": "TEST-ACCOUNT",
            "historical_confirmation_kind": None,
        }
        self.rows = ()
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters=None):
        if statement == _STAFF_PAYABLES_SQL:
            eligible = (self.row["due_date"] == parameters[0]
                        and self.row["payout_status"] in {"payable", "partially_paid"}
                        and self.row["export_amount_ntd"] > 0)
            self.rows = (dict(self.row),) if eligible else ()
        elif statement == _STAFF_PAYABLE_CASE_AUDIT_SQL:
            self.rows = (dict(self.row),) if parameters[0] == self.row["case_no"] else ()
        elif statement in {_HISTORICAL_STAFF_PAYABLE_PROJECTION_SQL, _CLIENT_REFUNDS_SQL}:
            self.rows = ()
        else:
            assert statement.startswith(("SET TRANSACTION", "START TRANSACTION"))

    def fetchall(self):
        return self.rows

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        self.commits += 1
        raise AssertionError("Accounts payable queries must not commit accounting facts")


class _Archive:
    def __init__(self):
        self.contents = []

    def save(self, year, filename, content, digest):
        self.contents.append(content)
        return ArchivedWorkbook("/test-archive/" + filename, digest)


def _client():
    connection = _Connection()
    archive = _Archive()
    application = AccountsPayableExportApplication(AccountsPayableExportWorkflow(
        MySqlStaffPayableExportSource(connection), MySqlClientRefundExportSource(connection),
        archive, lambda: _ReadOnlySnapshotComposition(connection),
        lambda: datetime(2026, 3, 1, tzinfo=timezone.utc),
    ))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(7, "finance", "Finance", "admin")
    app.dependency_overrides[get_accounts_payable_export_application] = lambda: application
    return TestClient(app), connection, archive


def test_partial_staff_balance_is_consistent_in_query_case_audit_and_download():
    client, connection, archive = _client()
    original = dict(connection.row)
    response = client.get(URL, params={"target_month": "2026-03"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["row_count"] == 1
    assert data["total_amount_ntd"] == 1500
    assert data["rows"][0]["amount_ntd"] == 1500
    assert data["rows"][0]["obligation_identities"] == [original["obligation_identity"]]

    response = client.get(URL + "/cases/CASE-P", params={"target_month": "2026-03"})
    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["amount_due_ntd"] == 20_000
    assert item["balance_ntd"] == 1500
    assert item["disposition"] == "selected_month"

    response = client.get(URL + "/export", params={"target_month": "2026-03"})
    assert response.status_code == 200
    assert archive.contents == [response.content]
    workbook = load_workbook(BytesIO(response.content))
    assert workbook.active["F3"].value == 1500
    assert connection.row == original
    assert connection.commits == 0
    assert connection.rollbacks == 3


def test_requery_reads_reduced_balance_and_removes_paid_items_without_changing_month_rules():
    client, connection, _ = _client()
    response = client.get(URL, params={"target_month": "2026-04"})
    assert response.status_code == 200
    assert response.json()["data"]["row_count"] == 0

    connection.row["export_amount_ntd"] = 500
    response = client.get(URL, params={"target_month": "2026-03"})
    assert response.status_code == 200
    assert response.json()["data"]["total_amount_ntd"] == 500

    connection.row.update(export_amount_ntd=0, payout_status="completed")
    response = client.get(URL, params={"target_month": "2026-03"})
    assert response.status_code == 200
    assert response.json()["data"]["rows"] == []
    response = client.get(URL + "/cases/CASE-P", params={"target_month": "2026-03"})
    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["balance_ntd"] == 0
    assert item["disposition"] == "paid_or_settled"
    assert connection.row["amount_due_ntd"] == 20_000
    assert connection.commits == 0
    assert connection.rollbacks == 4
