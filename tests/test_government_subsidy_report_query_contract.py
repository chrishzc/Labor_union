"""
File: test_government_subsidy_report_query_contract.py
Description: 驗證季度與年度補助查詢及匯出的Session、strict view、PII遮罩與aggregate。
"""
from datetime import date
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import finance_reports
from subsystems.access.authentication_session import AdminPrincipal


def _report():
    return {
        "general_citizen_rows": [{"序號": 1, "市府訂單號碼": "CASE-RPT-001", "補助資格": "一般市民", "服務開始": date(2026, 1, 1), "服務結束": date(2026, 1, 10), "補助時數": Decimal("40"), "補助天數": Decimal("5"), "服務天數": 10, "補助款金額": Decimal("12000"), "單價": Decimal("300"), "雇主": "王小美", "服務人員": "陳月嫂", "身分證字號": "A123456789", "地址": "完整地址", "簽領": ""}],
        "subsidized_citizen_rows": [],
        "xlsx_bytes": b"sensitive-workbook",
    }


def _app(authenticated=True):
    app = FastAPI()
    app.include_router(finance_reports.router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    if authenticated:
        app.dependency_overrides[require_admin] = lambda: AdminPrincipal(7, "reports", "Reports", "admin")
    return app


def test_quarterly_and_annual_reports_are_strict_and_redacted(monkeypatch):
    monkeypatch.setattr(finance_reports.reconciliation_register_query, "build_quarterly_subsidy_register", lambda *_: _report())
    monkeypatch.setattr(finance_reports.reconciliation_register_query, "build_annual_subsidy_summary", lambda *_: _report())
    client = TestClient(_app())
    quarterly = client.get("/api/v1/finance-reports/subsidy-reconciliation/quarterly", params={"application_year": 2026, "quarter": 1})
    annual = client.get("/api/v1/finance-reports/subsidy-reconciliation/annual", params={"application_year": 2026})
    quarterly_export = client.get("/api/v1/finance-reports/subsidy-reconciliation/quarterly/export", params={"application_year": 2026, "quarter": 1})
    annual_export = client.get("/api/v1/finance-reports/subsidy-reconciliation/annual/export", params={"application_year": 2026})
    assert quarterly.status_code == annual.status_code == 200
    assert quarterly_export.status_code == annual_export.status_code == 200
    assert quarterly.json()["data"]["period_kind"] == "quarterly"
    assert annual.json()["data"]["quarter"] is None
    row = quarterly.json()["data"]["partitions"][0]["rows"][0]
    assert row["employer_name"] == "王小美"
    assert row["identity_card"] == "A123456789"
    assert row["address"] == "完整地址"
    assert quarterly.json()["data"]["total_amount_ntd"] == 12000
    assert "A123456789" in quarterly.text
    assert "完整地址" in quarterly.text
    assert "xlsx_bytes" not in quarterly.text


def test_subsidy_report_requires_admin_before_builder(monkeypatch):
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setattr(finance_reports.reconciliation_register_query, "build_annual_subsidy_summary", lambda *_: (_ for _ in ()).throw(AssertionError("builder must not run")))
    response = TestClient(_app(authenticated=False)).get("/api/v1/finance-reports/subsidy-reconciliation/annual", params={"application_year": 2026})
    assert response.status_code == 401


def test_subsidy_report_exports_require_admin_before_builder(monkeypatch):
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    def blocked_builder(*_):
        raise AssertionError("builder must not run")

    monkeypatch.setattr(finance_reports.reconciliation_register_query, "build_quarterly_subsidy_register", blocked_builder)
    monkeypatch.setattr(finance_reports.reconciliation_register_query, "build_annual_subsidy_summary", blocked_builder)
    client = TestClient(_app(authenticated=False))

    quarterly = client.get(
        "/api/v1/finance-reports/subsidy-reconciliation/quarterly/export",
        params={"application_year": 2026, "quarter": 1},
    )
    annual = client.get(
        "/api/v1/finance-reports/subsidy-reconciliation/annual/export",
        params={"application_year": 2026},
    )

    assert quarterly.status_code == annual.status_code == 401
