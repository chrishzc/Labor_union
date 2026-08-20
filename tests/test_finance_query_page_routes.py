"""
File: test_finance_query_page_routes.py
Description: 驗證Finance query GET的enabled-principal依賴與AP server-side masking。
"""
from inspect import signature
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.params import Depends as DependsParam
from fastapi.testclient import TestClient

from api.dependencies.accounts_payable_export import get_accounts_payable_export_application
from api.dependencies.admin_auth import require_admin
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import client_receipt_reconciliation, finance_import, finance_reports, staff_payout
from shared_kernel.money import MoneyNTD
from subsystems.access.authentication_session import AdminPrincipal


class _Application:
    def query(self, _target_date):
        return (
            SimpleNamespace(
                payment_date=finance_reports.date(2026, 8, 15),
                payment_type="staff_payable",
                recipient_name="去敏受款人",
                bank_code="812",
                bank_account="123456789012",
                amount=MoneyNTD(5000),
                obligation_identities=("OBL-1",),
                case_numbers=("CASE-FIN-001",),
                recipient_identity_card="A123456789",
            ),
        )


def _dependency(function, parameter):
    value = signature(function).parameters[parameter].default
    assert isinstance(value, DependsParam)
    return value.dependency


def test_query_routes_use_enabled_principal_dependency():
    assert _dependency(client_receipt_reconciliation.query_receipt_facts, "principal") is require_admin
    assert _dependency(staff_payout.query_staff_payables, "principal") is require_admin
    for function in (
        finance_import.list_finance_import_batches,
        finance_import.get_finance_import_batch_manifest,
        finance_import.list_finance_import_review_rows,
        finance_import.list_finance_import_reprocess_runs,
    ):
        assert _dependency(function, "principal") is require_admin


def test_accounts_payable_query_requires_admin_and_masks_sensitive_values(monkeypatch):
    app = FastAPI()
    app.include_router(finance_reports.router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(7, "finance", "Finance", "admin")
    app.dependency_overrides[get_accounts_payable_export_application] = _Application
    response = TestClient(app).get(
        "/api/v1/finance-reports/accounts-payable",
        params={"target_month": "2026-08", "view": "summary"},
        headers={"X-Correlation-ID": "finance-ap-query"},
    )
    assert response.status_code == 200
    row = response.json()["data"]["rows"][0]
    assert row["bank_account_masked"].endswith("9012")
    assert row["recipient_identity_card_masked"] == "A*********"
    assert "123456789012" not in response.text
    assert "A123456789" not in response.text
