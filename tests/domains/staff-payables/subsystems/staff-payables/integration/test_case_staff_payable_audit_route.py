from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.accounts_payable_export import get_accounts_payable_export_application
from api.dependencies.admin_auth import require_admin
from api.routes import finance_reports
from shared_kernel.money import MoneyNTD
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff_payables.accounts_payable_export import CaseStaffPayableAuditItem


class _CaseAuditApplication:
    def __init__(self):
        self.calls = []

    def query_case(self, case_no, target_payment_date):
        self.calls.append((case_no, target_payment_date))
        return (
            CaseStaffPayableAuditItem(
                case_no=case_no,
                staff_id=7,
                recipient_name="月嫂甲",
                obligation_identity="service:CASE-1:assignment:7",
                amount_due=MoneyNTD(42_000),
                balance=MoneyNTD(42_000),
                order_due_date=date(2026, 10, 15),
                effective_due_date=date(2026, 10, 15),
                source="formal_obligation",
                disposition="selected_month",
                reason="本月正式月嫂應付款。",
            ),
            CaseStaffPayableAuditItem(
                case_no=case_no,
                staff_id=None,
                recipient_name=None,
                obligation_identity=None,
                amount_due=None,
                balance=None,
                order_due_date=None,
                effective_due_date=None,
                source="order_facts",
                disposition="date_not_formed",
                reason="尚未形成月嫂應付款日期。",
            ),
        )


def test_case_audit_get_returns_source_dates_reason_and_preserves_unknown_values():
    application = _CaseAuditApplication()
    app = FastAPI()
    app.include_router(finance_reports.router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        7, "finance", "Finance", "admin"
    )
    app.dependency_overrides[get_accounts_payable_export_application] = lambda: application

    response = TestClient(app).get(
        "/api/v1/finance-reports/accounts-payable/cases/CASE-1",
        params={"target_month": "2026-10"},
    )

    assert response.status_code == 200
    assert application.calls == [("CASE-1", date(2026, 10, 15))]
    data = response.json()["data"]
    assert data["target_payment_date"] == "2026-10-15"
    assert data["items"][0] == {
        "case_no": "CASE-1",
        "staff_id": 7,
        "recipient_name": "月嫂甲",
        "obligation_identity": "service:CASE-1:assignment:7",
        "amount_due_ntd": 42_000,
        "balance_ntd": 42_000,
        "order_due_date": "2026-10-15",
        "effective_due_date": "2026-10-15",
        "source": "formal_obligation",
        "disposition": "selected_month",
        "reason": "本月正式月嫂應付款。",
    }
    assert data["items"][1]["amount_due_ntd"] is None
    assert data["items"][1]["balance_ntd"] is None
    assert data["items"][1]["effective_due_date"] is None
