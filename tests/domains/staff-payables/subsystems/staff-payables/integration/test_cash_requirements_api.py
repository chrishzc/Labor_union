"""Authenticated bounded cash-planning GET; existing export entry remains independent."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.dependencies.accounts_payable_export import get_cash_requirements_application
from api.dependencies.admin_auth import require_admin
from api.routes.finance_reports import router
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff_payables.cash_requirements_query import CashRequirementPage, CashRequirementRow


URL = "/api/v1/finance-reports/accounts-payable/cash-requirements"


class Application:
    def __init__(self): self.calls = []
    def query(self, **options):
        self.calls.append(options)
        return CashRequirementPage((CashRequirementRow("C-1:unknown", "C-1", None, "staff_payable",
            "estimated", "missing_payroll", None, None, None, False, ("金額待確認",)),), None)


def client(application, authenticated=True):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_cash_requirements_application] = lambda: application
    if authenticated:
        app.dependency_overrides[require_admin] = lambda: AdminPrincipal(7, "finance", "Finance", "admin")
    return TestClient(app)


def test_authenticated_query_preserves_unknowns_and_does_not_expose_bank_details():
    application = Application()
    response = client(application).get(URL, params={"page_size": 2, "after_case_no": "C-0"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["rows"][0]["unpaid_amount_ntd"] is None
    assert data["rows"][0]["payment_date"] is None
    assert "bank_account" not in data["rows"][0]
    assert application.calls == [{"page_size": 2, "after_case_no": "C-0"}]


def test_query_rejects_unauthenticated_access_before_reading_sources(monkeypatch):
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    application = Application()
    assert client(application, False).get(URL).status_code == 401
    assert application.calls == []


def test_query_is_bounded_and_has_no_post_entry():
    application = Application()
    c = client(application)
    assert c.get(URL, params={"page_size": 201}).status_code == 422
    assert c.post(URL).status_code == 405
    assert application.calls == []
