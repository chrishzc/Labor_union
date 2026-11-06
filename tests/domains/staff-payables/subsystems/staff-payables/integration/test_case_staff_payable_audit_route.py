from datetime import date
import os
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.accounts_payable_export import get_accounts_payable_export_application
from api.dependencies.admin_auth import require_admin, require_system_admin
from api.routes import accounting_differences, finance_reports
from domains.orders.historical_adoption import HistoricalOrderSourceStatus
from infrastructure.mysql.historical_assignment_writer import MySqlHistoricalAssignmentWriter
from infrastructure.mysql.historical_order_adoption_repository import MySqlHistoricalOrderAdoptionRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.money import MoneyNTD
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.historical_adoption_workflow import HistoricalOrderAdoptionRequest, HistoricalOrderAdoptionWorkflow
from subsystems.orders.historical_order_workbook import HistoricalCaregiverSource, HistoricalOrderWorkbookRow
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


@pytest.mark.skipif(
    not os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE", "").startswith("lu_test_")
    or os.getenv("DB_DATABASE") != os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE"),
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)
def test_historical_lookup_record_unpaid_and_correct_due_date():
    token = uuid4().hex[:12]
    case_no, staff_name = f"PAYABLE-REVIEW-{token}", f"合成月嫂-{token}"
    _adopt_synthetic_case(case_no, staff_name, token)
    app = FastAPI()
    app.include_router(finance_reports.router)
    app.include_router(accounting_differences.router)
    principal = AdminPrincipal(7, "finance", "Finance", "system_admin")
    app.dependency_overrides[require_admin] = lambda: principal
    app.dependency_overrides[require_system_admin] = lambda: principal
    lookup = "/api/v1/finance-reports/accounts-payable/historical-lookup"
    record = f"/api/v1/orders/{case_no}/payroll/historical-unpaid-payable"

    with TestClient(app) as client:
        def find(keyword, month):
            response = client.get(lookup, params={"keyword": keyword, "target_month": month})
            assert response.status_code == 200, response.text
            return response.json()["data"][0]

        missing = find(staff_name, "2026-10")
        assert missing["case_no"] == case_no
        assert missing["staff_id"] > 0
        assert missing["disposition"] == "date_not_formed"
        assert missing["balance_ntd"] is None
        assert missing["current_event_id"] is None
        original = {
            "staff_id": missing["staff_id"], "amount_ntd": 12000, "due_date": None,
            "evidence": "Synthetic payroll register and payment history", "confirmed_unpaid": True, "key": token,
        }
        assert client.post(record, json={**original, "confirmed_unpaid": False}).status_code == 422
        response = client.post(record, json=original)
        assert response.status_code == 200, response.text
        assert client.post(record, json=original).json()["data"] == response.json()["data"]
        assert client.post(record, json={**original, "key": token + "-duplicate"}).status_code == 409

        undated = find(case_no, "2026-10")
        assert undated["disposition"] == "date_not_formed"
        assert undated["balance_ntd"] == 12000
        correction = {
            **original, "due_date": "2026-10-15", "key": token + "-correction",
            "obligation_identity": undated["obligation_identity"], "expected_event_id": undated["current_event_id"],
        }
        assert client.post(record, json={**correction, "expected_event_id": 1 if undated["current_event_id"] != 1 else 2}).status_code == 409
        response = client.post(record, json=correction)
        assert response.status_code == 200, response.text
        assert find(case_no, "2026-10")["disposition"] == "blocked"
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO staff_bank_accounts(staff_id,bank_code,account_no,is_primary) VALUES (%s,'807',%s,1)",
                    (missing["staff_id"], f"9{missing['staff_id']:013d}"),
                )
            connection.commit()
        finally:
            connection.close()
        assert find(case_no, "2026-09")["disposition"] == "other_month"
        current = find(case_no, "2026-10")
        assert current["disposition"] == "selected_month"
        assert current["balance_ntd"] == 12000
        assert current["obligation_identity"] != undated["obligation_identity"]
        exported = client.get("/api/v1/finance-reports/accounts-payable", params={"target_month": "2026-10"})
        assert exported.status_code == 200, exported.text
        assert sum(row["amount_ntd"] for row in exported.json()["data"]["rows"] if case_no in row["case_numbers"]) == 12000


def _adopt_synthetic_case(case_no, staff_name, token):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'合成客戶')", (case_no,))
            cursor.execute(
                "INSERT INTO orders(case_no,client_id,status,lifecycle_version,service_start_time,service_end_time,service_end_day_offset) "
                "VALUES (%s,%s,'洽談中',0,'09:00:00','13:00:00',0)", (case_no, cursor.lastrowid),
            )
            cursor.execute("INSERT INTO staff(name,identity_card) VALUES (%s,%s)", (staff_name, f"W{token[:9]}"))
        connection.commit()
        start, end = date(2025, 1, 2), date(2025, 1, 31)
        row = HistoricalOrderWorkbookRow(
            2, f"synthetic-source:{token}", fingerprint_payload({"case": case_no}).value,
            case_no, "合成客戶", HistoricalOrderSourceStatus.DEPOSIT_PAID, start, end,
            (HistoricalCaregiverSource(1, staff_name, start, end, True, ()),), (),
        )
        workflow = HistoricalOrderAdoptionWorkflow(
            MySqlHistoricalOrderAdoptionRepository(connection), lambda: MySqlUnitOfWork(connection),
            MySqlHistoricalAssignmentWriter(connection),
        )
        preview = workflow.preview(row)
        workflow.apply(HistoricalOrderAdoptionRequest(
            row, preview.fingerprint, f"payable-review:{token}", "test", "synthetic source", token,
        ))
        assert preview.after_status == "歷史訂單－服務完成"
    finally:
        connection.close()
