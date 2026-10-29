"""Authenticated, read-only finance identity projection."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.client_payments import router
from api.dependencies.admin_auth import require_admin
from api.dependencies.client_payments import get_client_finance_query_application
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.client_payments_query import ClientFinanceQueryApplication, FinanceCaseCategory


def test_case_categories_require_auth_and_return_bounded_owner_values(monkeypatch):
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    class Repository:
        def query_categories(self):
            return (FinanceCaseCategory("115000099", "non_citizen"), FinanceCaseCategory("115000001", "subsidy"))
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_client_finance_query_application]=lambda:ClientFinanceQueryApplication(Repository())
    with TestClient(app) as client:
        assert client.get("/api/v1/client-payments/case-categories").status_code in {401,403}
        app.dependency_overrides[require_admin]=lambda:AdminPrincipal(1,"synthetic","Synthetic","system_admin")
        response=client.get("/api/v1/client-payments/case-categories")
        assert response.status_code==200
        assert response.json()["data"]==[{"case_no":"115000099","category":"non_citizen"},
                                         {"case_no":"115000001","category":"subsidy"}]
