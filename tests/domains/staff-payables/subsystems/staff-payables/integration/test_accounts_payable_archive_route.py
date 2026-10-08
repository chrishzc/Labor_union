"""Access control for accounts-payable archive metadata."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.accounts_payable_export import (
    get_accounts_payable_export_application,
)
from api.dependencies.admin_auth import require_admin
from api.routes import finance_reports
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff_payables.accounts_payable_export import ArchivedWorkbookRecord


ARCHIVE_URL = "/api/v1/finance-reports/accounts-payable/archive"


class _ArchiveApplication:
    def __init__(self):
        self.years = []

    def query_archive(self, year):
        self.years.append(year)
        return (
            ArchivedWorkbookRecord(
                filename="accounts-payable-2026-10.xlsx",
                absolute_path="/private/accounts-payable-2026-10.xlsx",
                sha256="a" * 64,
                size_bytes=1234,
            ),
        )


def _client(application):
    app = FastAPI()
    app.include_router(finance_reports.router)
    app.dependency_overrides[get_accounts_payable_export_application] = (
        lambda: application
    )
    return app, TestClient(app)


def test_archive_list_rejects_unauthenticated_requests(monkeypatch):
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    application = _ArchiveApplication()
    _, client = _client(application)

    response = client.get(ARCHIVE_URL, params={"year": 2026})

    assert response.status_code == 401
    assert application.years == []


def test_archive_list_allows_authenticated_admin_and_omits_absolute_paths():
    application = _ArchiveApplication()
    app, client = _client(application)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        7, "finance", "Finance", "admin"
    )

    response = client.get(ARCHIVE_URL, params={"year": 2026})

    assert response.status_code == 200
    assert application.years == [2026]
    assert response.json()["data"] == {
        "year": 2026,
        "records": [{
            "filename": "accounts-payable-2026-10.xlsx",
            "sha256": "a" * 64,
            "size_bytes": 1234,
        }],
    }
