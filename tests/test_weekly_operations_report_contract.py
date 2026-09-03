"""
File: test_weekly_operations_report_contract.py
Description: 驗證營運週報週界、彙總、遮罩、正式工時、strict API 與三分頁 XLSX。
"""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from api.dependencies.admin_auth import require_admin
from api.dependencies.operations_reports import get_weekly_operations_report_query
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import operations_reports
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.reporting.weekly_operations_report_query import (
    SubsidyFact,
    SubsidyFacts,
    WeeklyCaseFact,
    WeeklyOperationsReportQuery,
    WeeklyServiceFact,
)
from infrastructure.mysql.weekly_operations_report_query_adapter import _CASE_FACTS_SQL


class _Facts:
    def list_case_facts(self, start_date, end_date):
        assert (start_date, end_date) == (date(2026, 8, 20), date(2026, 8, 26))
        return [
            WeeklyCaseFact(
                7, "115000007", datetime(2026, 8, 18, 9), "王小美", "一般市民", None,
                "東區", "服務中", 20, 8, date(2026, 8, 10), date(2026, 9, 4),
            ),
            WeeklyCaseFact(
                8, "115000008", datetime(2026, 8, 19, 10), "林大華", None, "資格不符",
                "北區", None, None, None, None, None,
            ),
        ]

    def list_service_facts(self, start_date, end_date):
        return [
            WeeklyServiceFact(
                31, "115000007", "王小美", "陳月嫂", date(2026, 8, 10), date(2026, 9, 4),
                8, 5, "服務中", "active",
            ),
        ]

    def list_subsidy_facts(self, start_date, end_date):
        assert (start_date, end_date) == (date(2026, 8, 20), date(2026, 8, 26))
        return SubsidyFacts(
            general=(
                SubsidyFact(
                    1, "115000007", "一般市民", date(2026, 8, 10), date(2026, 8, 20),
                    Decimal("40"), Decimal("5"), 20, 12000, 300,
                    "王小美", "陳月嫂", "A123456789", "完整地址",
                ),
            ),
            subsidized=(),
        )


def _query():
    return WeeklyOperationsReportQuery(
        _Facts(),
        lambda: datetime(2026, 8, 23, 12, tzinfo=TAIPEI_TIME_ZONE),
    )


def _app():
    app = FastAPI()
    app.include_router(operations_reports.router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(7, "reports", "Reports", "admin")
    app.dependency_overrides[get_weekly_operations_report_query] = _query
    return app


def test_weekly_query_is_redacted_and_uses_official_work_days():
    response = TestClient(_app()).get(
        "/api/v1/operations-reports/weekly",
        params={"start_date": "2026-08-20", "end_date": "2026-08-26"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "operations-report.v2"
    assert data["period"] == {
        "start_date": "2026-08-20",
        "end_date": "2026-08-26",
        "timezone": "Asia/Taipei",
        "period_label": "2026-08-20 ~ 2026-08-26",
    }
    assert data["summary"]["application_count"] == 2
    assert data["summary"]["general_eligible_count"] == 1
    assert data["summary"]["rejection_unpartitioned_count"] == 1
    assert data["summary"]["promotion_count"] is None
    assert data["service_rows"][0]["weekly_work_days"] == 5
    assert data["service_rows"][0]["weekly_hours"] == 40
    assert data["case_rows"][0]["applicant_name_masked"] == "王**"
    assert data["subsidy_partitions"][0]["rows"][0]["identity_card_masked"] == "A*********"
    assert "王小美" not in response.text
    assert "A123456789" not in response.text
    assert "完整地址" not in response.text


def test_operations_report_rejects_inverted_date_range():
    response = TestClient(_app()).get(
        "/api/v1/operations-reports/weekly",
        params={"start_date": "2026-08-26", "end_date": "2026-08-20"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "weekly_operations_report_invalid"


def test_operations_report_rejects_legacy_week_start_parameter():
    response = TestClient(_app()).get(
        "/api/v1/operations-reports/weekly",
        params={"start_date": "2026-08-20", "end_date": "2026-08-26", "week_start": "2026-08-20"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "weekly_operations_report_invalid"


def test_weekly_query_retains_missing_application_date_as_typed_quality_issue():
    class MissingDateFacts(_Facts):
        def list_case_facts(self, start_date, end_date):
            return [
                WeeklyCaseFact(
                    9, "OPS96-WEEKLY-D-MISSING-DATE", None, "林大華", "一般市民", None,
                    "北區", "洽談中", None, None, None, None,
                ),
            ]

    def query():
        return WeeklyOperationsReportQuery(
            MissingDateFacts(),
            lambda: datetime(2026, 8, 23, 12, tzinfo=TAIPEI_TIME_ZONE),
        )

    app = _app()
    app.dependency_overrides[get_weekly_operations_report_query] = query
    response = TestClient(app).get(
        "/api/v1/operations-reports/weekly",
        params={"start_date": "2026-08-20", "end_date": "2026-08-26"},
    )
    assert response.status_code == 200
    row = response.json()["data"]["case_rows"][0]
    assert row["application_date"] is None
    assert "application_date_missing" in row["data_quality_codes"]


def test_case_source_retains_rows_without_application_date_for_typed_quality_review():
    assert "OR c.created_at IS NULL" in _CASE_FACTS_SQL


def test_weekly_export_has_fixed_three_sheets_and_summary_without_pii():
    response = TestClient(_app()).get(
        "/api/v1/operations-reports/weekly/export",
        params={"start_date": "2026-08-20", "end_date": "2026-08-26"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "2026-08-20_2026-08-26" in response.headers["content-disposition"]
    workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    assert workbook.sheetnames == ["週報案件受理總表", "補助案件統計表", "每週服務中與工時"]
    case_values = list(workbook["週報案件受理總表"].values)
    assert case_values[0][:2] == ("報表期間", "2026-08-20 ~ 2026-08-26")
    assert "未登錄" in case_values[1]
    workbook_text = " ".join(str(value) for sheet in workbook for row in sheet.values for value in row if value is not None)
    assert "王小美" not in workbook_text
    assert "A123456789" not in workbook_text
    assert "完整地址" not in workbook_text
